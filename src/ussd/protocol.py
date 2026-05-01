"""
USSD Protocol Handler
Parses USSD codes, formats responses, and manages USSD session state.

Supports both legacy one-shot requests like *165*2*0700000001*500# and
menu-driven sessions backed by the ussd_sessions table.
"""
import logging
import time
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass
class USSDRequest:
    """Parsed USSD request"""
    code: str  # 165 (service code)
    operation: str  # 1=deposit, 2=withdraw, 3=balance, 4=mini_statement
    phone_number: str
    amount: Optional[float] = None
    additional_params: List[str] = None
    raw_input: str = ""
    
    def __post_init__(self):
        if self.additional_params is None:
            self.additional_params = []


class USSDParser:
    """Parse and validate USSD requests"""
    
    # Operation codes
    OPERATIONS = {
        "1": "deposit",
        "2": "withdraw",
        "3": "check_balance",
        "4": "mini_statement",
    }
    
    OPERATION_CODES_REVERSE = {v: k for k, v in OPERATIONS.items()}
    
    @staticmethod
    def parse(ussd_input: str) -> Tuple[bool, Optional[USSDRequest], str]:
        """
        Parse USSD input string
        
        Format: *165*operation*phone*amount
        Example: *165*2*075346363*1000
        
        Args:
            ussd_input: Raw USSD input string
            
        Returns:
            (success: bool, request: USSDRequest or None, error_message: str)
        """
        try:
            # Strip surrounding asterisks and hash
            cleaned = ussd_input.strip('*#')
            
            # Split by asterisk
            parts = cleaned.split('*')
            
            if len(parts) < 3:
                return False, None, "Invalid USSD format. Use: *165*operation*phone*[amount]"
            
            service_code = parts[0]
            operation_code = parts[1]
            phone_number = parts[2]
            amount = None
            additional = []
            
            # Validate service code
            if service_code != "165":
                return False, None, f"Invalid service code {service_code}"
            
            # Validate operation code
            if operation_code not in USSDParser.OPERATIONS:
                return False, None, f"Invalid operation code {operation_code}. Use: 1=deposit, 2=withdraw, 3=balance, 4=statement"
            
            operation = USSDParser.OPERATIONS[operation_code]
            
            # Validate phone number format (basic)
            if not phone_number.startswith('0') or len(phone_number) < 10:
                return False, None, "Invalid phone number format"
            
            # Parse amount if present
            if len(parts) > 3 and parts[3]:
                try:
                    amount = float(parts[3])
                    if amount <= 0:
                        return False, None, "Amount must be positive"
                except ValueError:
                    return False, None, f"Invalid amount: {parts[3]}"
                
                # Check if operation requires amount
                if operation in ["check_balance", "mini_statement"]:
                    return False, None, f"{operation} does not require amount"
            else:
                # Check if operation requires amount
                if operation in ["withdraw", "deposit"]:
                    return False, None, f"{operation} requires amount"
            
            # Remaining parts as additional parameters
            if len(parts) > 4:
                additional = parts[4:]
            
            request = USSDRequest(
                code=service_code,
                operation=operation,
                phone_number=phone_number,
                amount=amount,
                additional_params=additional,
                raw_input=ussd_input
            )
            
            logger.debug(f"Parsed USSD: {operation} for {phone_number}, amount={amount}")
            return True, request, ""
            
        except Exception as e:
            logger.error(f"USSD parsing error: {str(e)}")
            return False, None, f"Parsing error: {str(e)}"


class USSDFormatter:
    """Format USSD responses"""

    @staticmethod
    def _format_amount(amount: float) -> str:
        """Format amounts with grouped thousands and no trailing zero noise."""
        try:
            quantized = Decimal(str(amount)).normalize()
            formatted = format(quantized, "f")
        except (InvalidOperation, ValueError):
            formatted = str(amount)

        if "." in formatted:
            whole, fraction = formatted.split(".", 1)
            whole = f"{int(whole):,}"
            fraction = fraction.rstrip("0")
            return f"{whole}.{fraction}" if fraction else whole

        try:
            return f"{int(formatted):,}"
        except ValueError:
            return formatted
    
    @staticmethod
    def success_response(
        operation: str,
        message: str,
        data: Optional[Dict] = None
    ) -> str:
        """
        Format successful response
        
        Args:
            operation: Operation code (1-4)
            message: Response message
            data: Additional data
            
        Returns:
            Formatted USSD response string
        """
        op_code = USSDParser.OPERATION_CODES_REVERSE.get(operation, "0")
        
        if data and "balance" in data:
            # For balance check
            return f"*165*{op_code}*Balance:{data['balance']}{data.get('currency', 'KES')}#"
        
        elif data and "transactions" in data:
            # For mini statement
            response = f"*165*{op_code}*Mini Statement:\n"
            for txn in data["transactions"][:5]:  # Last 5 transactions
                response += f"{txn['type']}: {txn['amount']} ({txn['timestamp'][:10]})\n"
            response += "#"
            return response
        
        else:
            # Generic success
            return f"*165*{op_code}*{message}#"
    
    @staticmethod
    def error_response(
        operation: str,
        error_message: str
    ) -> str:
        """
        Format error response
        
        Args:
            operation: Operation code
            error_message: Error message
            
        Returns:
            Formatted USSD error response
        """
        op_code = USSDParser.OPERATION_CODES_REVERSE.get(operation, "0")
        return f"*165*{op_code}*ERROR:{error_message}#"
    
    @staticmethod
    def pending_response(operation: str) -> str:
        """
        Format pending/async response
        
        Args:
            operation: Operation code
            
        Returns:
            Formatted USSD pending response
        """
        op_code = USSDParser.OPERATION_CODES_REVERSE.get(operation, "0")
        return f"*165*{op_code}*Request received. You will receive an SMS confirmation shortly.#"

    @staticmethod
    def session_response(message: str, continue_session: bool = True) -> str:
        """Format a menu-style USSD response."""
        prefix = "CON" if continue_session else "END"
        return f"{prefix} {message}"

    @staticmethod
    def main_menu() -> str:
        """Default USSD main menu."""
        return USSDFormatter.session_response(
            "Mobile Money\n"
            "1. Deposit Money\n"
            "2. Withdraw Money\n"
            "3. Check Balance\n"
            "4. Mini Statement\n"
            "0. Exit"
        )

    @staticmethod
    def amount_prompt(operation: str) -> str:
        """Prompt for an amount in a menu flow."""
        action = {
            "deposit": "deposit",
            "withdraw": "withdraw",
        }.get(operation, operation)
        return USSDFormatter.session_response(f"Enter amount to {action}")

    @staticmethod
    def confirm_prompt(operation: str, amount: float) -> str:
        """Prompt user to confirm a pending transaction."""
        return USSDFormatter.session_response(
            f"Confirm {operation} of {USSDFormatter._format_amount(amount)}?\n1. Yes\n2. No"
        )

    @staticmethod
    def session_end(message: str) -> str:
        """Format a terminating USSD response."""
        return USSDFormatter.session_response(message, continue_session=False)


class USSDSessionManager:
    """Manage persistent USSD session state"""

    DEFAULT_TTL_SECONDS = 300
    
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _payload(state: str, phone_number: str, account_id: Optional[int] = None, data: Optional[Dict] = None) -> Dict:
        return {
            "state": state,
            "phone_number": phone_number,
            "account_id": account_id,
            "data": data or {},
        }

    @staticmethod
    def parse_amount_input(raw_amount: str) -> Decimal:
        """Parse a USSD amount while allowing commas and whitespace separators."""
        cleaned = (raw_amount or "").strip().replace(",", "").replace("_", "")
        if not cleaned:
            raise InvalidOperation("Amount is required")

        if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
            raise InvalidOperation(f"Invalid amount: {raw_amount}")

        amount = Decimal(cleaned)
        if amount <= 0:
            raise InvalidOperation("Amount must be positive")
        return amount
    
    def create_session(self, db, phone_number: str, account_id: Optional[int] = None, server_id: Optional[str] = None):
        """Create a new persistent USSD session."""
        from src.models import USSDSession

        session = USSDSession(
            session_id=f"ussd_{phone_number}_{int(time.time() * 1000)}",
            phone_number=phone_number,
            account_id=account_id,
            session_state="MAIN_MENU",
            session_data=self._payload("MAIN_MENU", phone_number, account_id),
            created_at=self._now(),
            updated_at=self._now(),
            expires_at=self._now() + timedelta(seconds=self.ttl_seconds),
            server_id=server_id,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    def get_session(self, db, session_id: str):
        """Get session data by session id."""
        from src.models import USSDSession

        session = db.query(USSDSession).filter(USSDSession.session_id == session_id).first()
        if not session:
            return None
        if session.expires_at and session.expires_at <= self._now():
            self.end_session(db, session_id)
            return None
        return session

    def get_or_create_session(self, db, phone_number: str, account_id: Optional[int] = None, server_id: Optional[str] = None):
        """Return the active session for a phone number or create one."""
        from src.models import USSDSession

        session = db.query(USSDSession).filter(
            USSDSession.phone_number == phone_number,
            USSDSession.expires_at > self._now(),
        ).order_by(USSDSession.updated_at.desc()).first()

        if session:
            return session
        return self.create_session(db, phone_number, account_id=account_id, server_id=server_id)
    
    def update_session(self, db, session_id: str, state: str, data: Dict = None):
        """Update session state, payload, and expiry."""
        session = self.get_session(db, session_id)
        if not session:
            return None

        current_data = (session.session_data or {}).get("data", {})
        session.session_state = state
        session.session_data = self._payload(
            state,
            session.phone_number,
            session.account_id,
            {**current_data, **(data or {})},
        )
        session.updated_at = self._now()
        session.expires_at = self._now() + timedelta(seconds=self.ttl_seconds)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    def end_session(self, db, session_id: str):
        """End session and remove it from persistence."""
        from src.models import USSDSession

        session = db.query(USSDSession).filter(USSDSession.session_id == session_id).first()
        if not session:
            return False
        db.delete(session)
        db.commit()
        return True

    def cleanup_expired_sessions(self, db) -> int:
        """Remove expired sessions from storage."""
        from src.models import USSDSession

        deleted = db.query(USSDSession).filter(USSDSession.expires_at <= self._now()).delete()
        db.commit()
        return deleted


# Example usage
if __name__ == "__main__":
    test_cases = [
        "*165*2*075346363*1000#",  # Valid withdraw
        "*165*1*075346363*500#",   # Valid deposit
        "*165*3*075346363#",        # Valid balance check
        "*165*2*075346363#",        # Missing amount
        "*165*9*075346363*1000#",  # Invalid operation
        "*123*2*075346363*1000#",   # Invalid service code
    ]
    
    parser = USSDParser()
    formatter = USSDFormatter()
    
    for test in test_cases:
        print(f"\nInput: {test}")
        success, request, error = parser.parse(test)
        
        if success:
            print(f"  Operation: {request.operation}")
            print(f"  Phone: {request.phone_number}")
            print(f"  Amount: {request.amount}")
            
            # Example response
            if request.operation == "check_balance":
                response = formatter.success_response(
                    "check_balance",
                    "Balance check",
                    {"balance": 5000, "currency": "KES"}
                )
            else:
                response = formatter.success_response(
                    request.operation,
                    f"{request.operation.title()} successful"
                )
            print(f"  Response: {response}")
        else:
            print(f"  ERROR: {error}")
            response = formatter.error_response("0", error)
            print(f"  Response: {response}")
