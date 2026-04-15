"""
USSD Protocol Handler
Parses USSD codes and formats responses
Code format: *165*operation*phone*amount*additional_params
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

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


class USSDSessionManager:
    """Manage USSD session state"""
    
    def __init__(self):
        # In-memory session storage (use Redis in production)
        self.sessions: Dict[str, Dict] = {}
    
    def create_session(self, phone_number: str) -> str:
        """Create a new USSD session"""
        session_id = f"ussd_{phone_number}_{int(__import__('time').time())}"
        self.sessions[session_id] = {
            "phone": phone_number,
            "state": "menu",
            "data": {}
        }
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data"""
        return self.sessions.get(session_id)
    
    def update_session(self, session_id: str, state: str, data: Dict = None):
        """Update session state and data"""
        if session_id in self.sessions:
            self.sessions[session_id]["state"] = state
            if data:
                self.sessions[session_id]["data"].update(data)
    
    def end_session(self, session_id: str):
        """End session"""
        if session_id in self.sessions:
            del self.sessions[session_id]


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
