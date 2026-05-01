"""
USSD Phone Client - Simulates feature phone USSD menu system
Allows users to interact with mobile money system using USSD codes (*165*...)
Works with text-based menus like real feature phones
"""

import os
import sys
import json
import time
import shutil
import textwrap
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import requests
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from client.mobile_money_client import MobileMoneyClient
from src.ussd.protocol import USSDParser, USSDFormatter


class USSDPhoneSession:
    """Manages USSD session state for a single phone user"""
    
    def __init__(self, phone_number: str, server_session_id: str = None):
        self.phone_number = phone_number
        self.session_id = server_session_id or f"{phone_number}_{int(datetime.now().timestamp() * 1000)}"
        self.account_id = None
        self.current_step = "initializing"
        self.input_buffer = {}
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.active = True
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
    
    def is_expired(self, timeout_minutes: int = 5) -> bool:
        """Check if session has expired"""
        elapsed = (datetime.now() - self.last_activity).total_seconds() / 60
        return elapsed > timeout_minutes
    
    def clear_buffer(self):
        """Clear input buffer for next transaction"""
        self.input_buffer = {}

    def update_step(self, step: str):
        """Update the current USSD step."""
        self.current_step = step
        self.update_activity()


class USSDPhoneClient:
    """USSD Phone Client - Interactive menu-driven interface"""
    
    # USSD Menu definitions
    MAIN_MENU = """
┌─────────────────────────────────┐
│  MOBILE MONEY SERVICE           │
│  *165*                          │
├─────────────────────────────────┤
│ 1. Deposit Money                │
│ 2. Withdraw Money               │
│ 3. Check Balance                │
│ 4. Transaction History          │
│ 5. Settings                     │
│ 0. Exit                         │
└─────────────────────────────────┘
Enter choice (0-5):
"""
    
    SETTINGS_MENU = """
┌─────────────────────────────────┐
│  SETTINGS                       │
├─────────────────────────────────┤
│ 1. View Account Info            │
│ 2. View Phone Number            │
│ 3. View Server Info             │
│ 4. Back to Main Menu            │
└─────────────────────────────────┘
Enter choice (1-4):
"""
    
    def __init__(self, phone_number: str = None, server_url: str = None, server_urls: List[str] = None):
        """
        Initialize USSD phone client
        
        Args:
            phone_number: User's phone number (default: interactive input)
            server_url: Single server base URL (optional, for backward compatibility)
            server_urls: List of server URLs to try (default: [localhost:8001, 8002, 8003])
        """
        self.phone_number = phone_number or self._prompt("Enter your phone number: ")
        
        # Use server_urls list, or fall back to single server_url, or use defaults
        if server_urls:
            self.server_urls = server_urls
        elif server_url:
            self.server_urls = [server_url]
        else:
            # Default to all available servers for discovery
            self.server_urls = [
                "http://localhost:8001",
                "http://localhost:8002",
                "http://localhost:8003"
            ]
        
        # Initialize RPC client with server list for automatic failover
        self.client = MobileMoneyClient(server_urls=self.server_urls)
        
        # Session management
        self.sessions: Dict[str, USSDPhoneSession] = {}
        self.current_session: Optional[USSDPhoneSession] = None
        self.last_server_response: Optional[Dict[str, str]] = None

    def _box_width(self) -> int:
        """Return a terminal-friendly box width."""
        try:
            terminal_width = shutil.get_terminal_size(fallback=(80, 20)).columns
        except OSError:
            terminal_width = 80
        return max(42, min(72, terminal_width - 4))
    
    def _prompt(self, message: str, allow_empty: bool = False) -> str:
        """Get user input with prompt"""
        while True:
            try:
                value = input(message).strip()
                if value or allow_empty:
                    return value
                print("Input cannot be empty. Please try again.")
            except (EOFError, KeyboardInterrupt):
                print("\n[Session terminated]")
                sys.exit(0)
    
    def _clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _display_response(self, title: str, message: str, data: dict = None):
        """Display response in USSD format"""
        width = self._box_width()
        inner_width = width - 4

        print("\n┌" + "─" * (width - 2) + "┐")
        centered_title = title.strip().upper()[:inner_width]
        print(f"│ {centered_title:^{inner_width}} │")
        print("├" + "─" * (width - 2) + "┤")

        wrapped_lines: List[str] = []
        for paragraph in (message or "").splitlines() or [""]:
            if paragraph.strip():
                wrapped = textwrap.wrap(
                    paragraph,
                    width=inner_width,
                    replace_whitespace=False,
                    drop_whitespace=False,
                )
                wrapped_lines.extend(wrapped or [""])
            else:
                wrapped_lines.append("")

        if not wrapped_lines:
            wrapped_lines = [""]

        for line in wrapped_lines:
            print(f"│ {line:<{inner_width}} │")

        if data:
            print("├" + "─" * (width - 2) + "┤")
            for key, value in data.items():
                entry = f"{key}: {value}"
                for line in textwrap.wrap(entry, width=inner_width) or [entry[:inner_width]]:
                    print(f"│ {line:<{inner_width}} │")

        print("└" + "─" * (width - 2) + "┘\n")

    def _parse_server_ussd_response(self, response_text: str) -> Tuple[str, str, bool]:
        """Convert a raw CON/END response into a display title and body."""
        if not response_text:
            return "USSD", "No response from server", False

        cleaned = response_text.strip()
        session_ended = False

        if cleaned.startswith("CON "):
            cleaned = cleaned[4:]
        elif cleaned.startswith("END "):
            cleaned = cleaned[4:]
            session_ended = True

        if not cleaned:
            return "USSD", "", session_ended

        lines = [line.rstrip() for line in cleaned.splitlines()]
        if session_ended:
            return "SESSION ENDED", cleaned, True

        if len(lines) == 1:
            return "USSD", lines[0], False

        title = lines[0][:27] or "USSD"
        message = "\n".join(lines[1:]).strip()
        return title, message or lines[0], False

    def _render_server_ussd_response(self, response_text: str):
        """Render a server USSD response returned as CON/END text."""
        title, message, session_ended = self._parse_server_ussd_response(response_text)
        self.last_server_response = {
            "title": title,
            "message": message,
            "session_ended": str(session_ended),
        }
        self._display_response(title, message)

    def _start_server_session(self) -> bool:
        """Open a server-backed USSD session and show the first menu."""
        if not self.current_session:
            self.current_session = USSDPhoneSession(self.phone_number)
            self.sessions[self.phone_number] = self.current_session

        print("📞 Dialing *165# to start USSD session...")
        result = self.client.start_ussd_session(self.phone_number)
        if not result.get("success"):
            self._display_response("ERROR", result.get("message", "Failed to start USSD session"))
            return False

        session_id = result.get("session_id")
        if not session_id:
            self._display_response("ERROR", "Server did not return a session ID")
            return False

        self.current_session.session_id = session_id
        self.current_session.update_step(result.get("session_state") or "MAIN_MENU")
        self.current_session.active = bool(result.get("session_active", True))

        ussd_response = result.get("ussd_response") or ""
        self._render_server_ussd_response(ussd_response)
        return True

    def _send_server_input(self, user_input: str) -> Dict:
        """Send a follow-up input to the active server USSD session."""
        if not self.current_session or not self.current_session.session_id:
            return {"success": False, "message": "No active session", "data": {}}

        result = self.client.continue_ussd_session(
            session_id=self.current_session.session_id,
            user_input=user_input,
            phone_number=self.phone_number,
        )

        if result.get("success"):
            self.current_session.update_step(result.get("session_state") or self.current_session.current_step)
            self.current_session.active = bool(result.get("session_active", True))

        return result
    
    def _start_session(self) -> bool:
        """Initialize session and load account"""
        try:
            # Try to discover server (find nearest server)
            print("🔍 Discovering nearest server...")
            result = self.client.discover_server(self.phone_number)
            
            if not result.get('success'):
                print(f"❌ Server discovery failed: {result.get('message')}")
                return False
            
            # Verify account exists in database
            print("🔍 Checking if account exists...")
            # Try to fetch account info by phone number via balance check
            account_check = self.client.check_balance(
                account_id=None,
                phone_number=self.phone_number
            )
            
            if not account_check.get('success'):
                # Account doesn't exist - offer to create one
                print(f"❌ Account not found for {self.phone_number}")
                print("\nWould you like to create a new account?")
                create = self._prompt("Enter 'yes' to create account or 'no' to exit: ").strip().lower()
                
                if create == 'yes':
                    account_name = self._prompt("Enter account holder name: ").strip()
                    initial_balance_str = self._prompt("Enter initial balance (optional, default: 0): ").strip()
                    try:
                        initial_balance = float(initial_balance_str) if initial_balance_str else 0.0
                    except ValueError:
                        print("❌ Invalid balance amount")
                        return False
                    
                    create_result = self.client.create_account(
                        phone_number=self.phone_number,
                        account_holder_name=account_name,
                        initial_balance=initial_balance
                    )
                    
                    if create_result.get('success'):
                        self._display_response(
                            "ACCOUNT CREATED",
                            "Your account has been created successfully!",
                            {"Phone": self.phone_number, 
                             "Balance": f"${initial_balance}"}
                        )
                    else:
                        print(f"❌ Failed to create account: {create_result.get('message')}")
                        return False
                else:
                    print("❌ Cannot proceed without an account")
                    return False
            else:
                # Account exists
                account_data = account_check.get('data', {})
                self._display_response(
                    "ACCOUNT FOUND",
                    "Account verified successfully!",
                    {"Phone": self.phone_number, 
                     "Balance": f"${account_data.get('balance', 0)}"}
                )
            
            # Create session
            self.current_session = USSDPhoneSession(self.phone_number)
            self.sessions[self.phone_number] = self.current_session
            
            server_info = result.get('data', {})
            self._display_response(
                "CONNECTED",
                f"Connected to {server_info.get('server_id', 'Unknown')}",
                {"Server": server_info.get('server_id'), 
                 "Port": server_info.get('port')}
            )
            
            print(f"📱 Welcome! Phone: {self.phone_number}")
            print(f"⏱️  Session started at {self.current_session.created_at.strftime('%H:%M:%S')}")
            
            return True
        
        except Exception as e:
            self._display_response("ERROR", f"Session initialization failed: {str(e)}")
            return False

    def _wait_for_async_operation(
        self,
        request_id: str,
        timeout_seconds: int = 20,
        poll_interval_seconds: float = 0.8,
    ) -> Dict:
        """Poll async operation status until completion, failure, or timeout."""
        start_time = time.time()

        while (time.time() - start_time) < timeout_seconds:
            status_result = self.client.get_operation_request_status(request_id)
            if not status_result.get("success"):
                return {
                    "success": False,
                    "message": status_result.get("message", "Failed to read request status"),
                    "data": {},
                }

            payload = status_result.get("data", {})
            processing_status = payload.get("processing_status")

            if processing_status == "completed":
                return {
                    "success": True,
                    "message": "Operation completed",
                    "data": payload.get("data", {}),
                }

            if processing_status == "failed":
                return {
                    "success": False,
                    "message": payload.get("error") or "Operation failed",
                    "data": payload.get("data", {}),
                }

            time.sleep(poll_interval_seconds)

        return {
            "success": False,
            "message": "Operation still processing. Please check again shortly.",
            "data": {},
        }
    
    def _handle_deposit(self):
        """Handle deposit operation"""
        print("\n💰 DEPOSIT MONEY")
        
        # Get amount
        while True:
            amount_str = self._prompt("Enter amount to deposit: ")
            try:
                amount = float(amount_str)
                if amount <= 0:
                    print("❌ Amount must be positive")
                    continue
                break
            except ValueError:
                print("❌ Invalid amount. Please enter a number")
        
        # Confirm
        confirm = self._prompt(f"Deposit {amount}? (yes/no): ").lower()
        if confirm != 'yes':
            self._display_response("CANCELLED", "Deposit operation cancelled")
            return
        
        # Process deposit
        print("⏳ Processing deposit...")
        result = self.client.deposit(
            account_id=self.phone_number,
            phone_number=self.phone_number,
            amount=amount
        )

        if not result['success']:
            self._display_response("ERROR", f"Deposit failed: {result['message']}")
            return

        request_id = result.get("request_id")
        if request_id:
            print("⏳ Finalizing deposit...")
            result = self._wait_for_async_operation(request_id)
        
        if result['success']:
            amount_value = result.get('data', {}).get('amount', amount)
            balance_value = result.get('data', {}).get('balance_after', 'N/A')
            self._display_response(
                "SUCCESS",
                "Deposit completed!",
                {
                    "Amount": f"{amount_value}",
                    "Balance": f"{balance_value}",
                    "Time": datetime.now().strftime("%H:%M:%S")
                }
            )
        else:
            self._display_response("ERROR", f"Deposit failed: {result['message']}")
    
    def _handle_withdraw(self):
        """Handle withdraw operation"""
        print("\n💵 WITHDRAW MONEY")
        
        # Get amount
        while True:
            amount_str = self._prompt("Enter amount to withdraw: ")
            try:
                amount = float(amount_str)
                if amount <= 0:
                    print("❌ Amount must be positive")
                    continue
                break
            except ValueError:
                print("❌ Invalid amount. Please enter a number")
        
        # Confirm
        confirm = self._prompt(f"Withdraw {amount}? (yes/no): ").lower()
        if confirm != 'yes':
            self._display_response("CANCELLED", "Withdrawal cancelled")
            return
        
        # Process withdrawal
        print("⏳ Processing withdrawal...")
        result = self.client.withdraw(
            account_id=self.phone_number,
            phone_number=self.phone_number,
            amount=amount
        )

        if not result['success']:
            self._display_response("ERROR", f"Withdrawal failed: {result['message']}")
            return

        request_id = result.get("request_id")
        if request_id:
            print("⏳ Finalizing withdrawal...")
            result = self._wait_for_async_operation(request_id)
        
        if result['success']:
            amount_value = result.get('data', {}).get('amount', amount)
            balance_value = result.get('data', {}).get('balance_after', 'N/A')
            self._display_response(
                "SUCCESS",
                "Withdrawal completed!",
                {
                    "Amount": f"{amount_value}",
                    "Balance": f"{balance_value}",
                    "Time": datetime.now().strftime("%H:%M:%S")
                }
            )
        else:
            self._display_response("ERROR", f"Withdrawal failed: {result['message']}")
    
    def _handle_balance(self):
        """Handle check balance operation"""
        print("⏳ Checking balance...")
        result = self.client.check_balance(
            account_id=self.phone_number,
            phone_number=self.phone_number
        )
        
        if result['success']:
            balance = result['data']['balance']
            self._display_response(
                "BALANCE",
                f"Your account balance:",
                {
                    "Phone": self.phone_number,
                    "Balance": f"${balance}"
                }
            )
        else:
            self._display_response("ERROR", f"Could not check balance: {result['message']}")
    
    def _handle_transactions(self):
        """Handle transaction history"""
        print("⏳ Fetching transactions...")
        result = self.client.get_transaction_history(
            account_id=self.phone_number,
            phone_number=self.phone_number,
            limit=5
        )
        
        if result['success']:
            transactions = result['data']['transactions']
            
            if not transactions:
                self._display_response("HISTORY", "No transactions yet")
                return
            
            print("\n┌─────────────────────────────────┐")
            print("│  RECENT TRANSACTIONS (Last 5)   │")
            print("├─────────────────────────────────┤")
            
            for i, txn in enumerate(transactions[:5], 1):
                op = "+" if txn['operation'] == 'deposit' else "-"
                amount = f"{op}{txn['amount']}"
                timestamp = txn['timestamp'][:10]  # Date only
                print(f"│ {i}. {txn['operation'][:8]:<8} {amount:>8} on {timestamp} │")
            
            print("└─────────────────────────────────┘\n")
        else:
            self._display_response("ERROR", f"Could not fetch transactions: {result['message']}")
    
    def _handle_settings(self):
        """Handle settings menu"""
        while True:
            print(self.SETTINGS_MENU)
            choice = self._prompt("Enter choice: ").strip()
            
            if choice == "1":
                # Account info
                result = self.client.get_account_details(
                    account_id=self.phone_number,
                    phone_number=self.phone_number
                )
                if result['success']:
                    account = result['data']['account']
                    self._display_response(
                        "ACCOUNT INFO",
                        "",
                        {
                            "Account ID": account['account_id'],
                            "Phone": account['phone_number'],
                            "Balance": f"{account['balance']}",
                            "Status": account['status'],
                            "Created": account['created_at'][:10]
                        }
                    )
                else:
                    self._display_response("ERROR", result['message'])
            
            elif choice == "2":
                # Phone number
                self._display_response(
                    "PHONE NUMBER",
                    f"Your registered phone:",
                    {"Number": self.phone_number}
                )
            
            elif choice == "3":
                # Server info
                result = self.client.discover_server(self.phone_number)
                if result['success']:
                    server = result['data']
                    self._display_response(
                        "SERVER INFO",
                        "Connected to:",
                        {
                            "Server": server.get('server_id'),
                            "Port": server.get('port'),
                            "Status": "Online"
                        }
                    )
                else:
                    self._display_response("ERROR", result['message'])
            
            elif choice == "4":
                break
            
            else:
                print("❌ Invalid choice. Please try again.")
    
    def _process_main_menu(self):
        """Drive a real server-backed USSD session until it ends."""
        if not self.current_session:
            self._display_response("ERROR", "Session is not initialized")
            return

        if not self._start_server_session():
            return

        while self.current_session and self.current_session.active:
            if self.current_session.is_expired():
                self._display_response("SESSION EXPIRED", "Your local session timed out")
                break

            print("\nEnter USSD reply exactly as shown in the menu.")
            print("Type 0 to exit the USSD session.")
            choice = self._prompt("Reply").strip()

            if not choice:
                print("❌ Input cannot be empty")
                continue

            self.current_session.update_activity()
            result = self._send_server_input(choice)

            if not result.get("success"):
                self._display_response("ERROR", result.get("message", "USSD request failed"))
                break

            ussd_response = result.get("ussd_response") or ""
            self._render_server_ussd_response(ussd_response)

            if result.get("session_id"):
                self.current_session.session_id = result["session_id"]

            if not result.get("session_active", True):
                self.current_session.active = False
                print("\n[Session ended on the server. Final message shown above.]\n")
                break

        if self.current_session:
            self.current_session.clear_buffer()
            self.current_session.active = False
    
    def run(self):
        """Main USSD client loop"""
        print("\n" + "="*35)
        print("  MOBILE MONEY USSD CLIENT")
        print("="*35)
        
        # Initialize session
        if not self._start_session():
            print("❌ Failed to start session. Make sure the server is running.")
            print(f"   Server URLs tried: {', '.join(self.server_urls)}")
            return
        
        # Run main menu
        try:
            self._process_main_menu()
        except KeyboardInterrupt:
            print("\n\n[Session interrupted]")
        except Exception as e:
            print(f"\n❌ Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
        
        # Cleanup
        if self.phone_number in self.sessions:
            del self.sessions[self.phone_number]
        
        print("\n✓ Session closed\n")


def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="USSD Phone Client - Mobile Money System"
    )
    parser.add_argument(
        "--phone",
        help="Phone number (optional, will be prompted if not provided)",
        type=str
    )
    parser.add_argument(
        "--servers",
        help="Comma-separated server URLs (default: auto-discover from all available servers)",
        type=str,
        default=None
    )
    
    args = parser.parse_args()
    
    # Parse server list if provided
    server_urls = None
    if args.servers:
        server_urls = [s.strip() for s in args.servers.split(',')]
    
    # Create and run client (uses distributed hashing for auto-discovery)
    client = USSDPhoneClient(
        phone_number=args.phone,
        server_urls=server_urls  # None = use defaults [8001, 8002, 8003]
    )
    client.run()


if __name__ == "__main__":
    main()
