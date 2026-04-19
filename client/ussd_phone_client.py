"""
USSD Phone Client - Simulates feature phone USSD menu system
Allows users to interact with mobile money system using USSD codes (*165*...)
Works with text-based menus like real feature phones
"""

import os
import sys
import json
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
    
    def __init__(self, phone_number: str):
        self.phone_number = phone_number
        self.session_id = f"{phone_number}_{int(datetime.now().timestamp() * 1000)}"
        self.account_id = None
        self.current_step = "main_menu"  # Current menu state
        self.input_buffer = {}  # Temporary storage for multi-step operations
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
    
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
    
    def __init__(self, phone_number: str = None, server_url: str = None):
        """
        Initialize USSD phone client
        
        Args:
            phone_number: User's phone number (default: interactive input)
            server_url: Server base URL (default: http://localhost:8001)
        """
        self.phone_number = phone_number or self._prompt("Enter your phone number: ")
        self.server_url = server_url or "http://localhost:8001"
        
        # Initialize RPC client
        self.client = MobileMoneyClient(base_url=self.server_url)
        
        # Session management
        self.sessions: Dict[str, USSDPhoneSession] = {}
        self.current_session: Optional[USSDPhoneSession] = None
    
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
        print(f"\n┌─────────────────────────────────┐")
        print(f"│  {title:<27}  │")
        print(f"├─────────────────────────────────┤")
        
        # Wrap message text
        lines = message.split('\n')
        for line in lines:
            # Simple text wrapping
            while len(line) > 30:
                print(f"│ {line[:30]:<30}  │")
                line = line[30:]
            if line:
                print(f"│ {line:<30}  │")
        
        if data:
            print(f"├─────────────────────────────────┤")
            for key, value in data.items():
                key_str = str(key)[:12]
                val_str = str(value)[:16]
                print(f"│ {key_str}: {val_str:<22} │")
        
        print(f"└─────────────────────────────────┘\n")
    
    def _start_session(self) -> bool:
        """Initialize session and load account"""
        try:
            # Create session
            self.current_session = USSDPhoneSession(self.phone_number)
            self.sessions[self.phone_number] = self.current_session
            
            # Try to discover server (find nearest server)
            print("🔍 Discovering nearest server...")
            result = self.client.discover_server(self.phone_number)
            
            if not result.get('success'):
                print(f"❌ Server discovery failed: {result.get('message')}")
                return False
            
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
        
        if result['success']:
            self._display_response(
                "SUCCESS",
                "Deposit completed!",
                {
                    "Amount": f"{result['data']['amount']}",
                    "Balance": f"{result['data']['balance_after']}",
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
        
        if result['success']:
            self._display_response(
                "SUCCESS",
                "Withdrawal completed!",
                {
                    "Amount": f"{result['data']['amount']}",
                    "Balance": f"{result['data']['balance_after']}",
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
            account_id = result['data']['account_id']
            self._display_response(
                "BALANCE",
                f"Your account balance:",
                {
                    "Phone": self.phone_number,
                    "Balance": f"${balance}",
                    "Account": account_id
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
        """Process main menu selection"""
        while True:
            if not self.current_session:
                break
            
            self.current_session.update_activity()
            
            # Check session expiry
            if self.current_session.is_expired():
                self._display_response("SESSION EXPIRED", "Your session has expired")
                break
            
            print(self.MAIN_MENU)
            choice = self._prompt("Enter choice: ").strip()
            
            if choice == "1":
                self._handle_deposit()
            elif choice == "2":
                self._handle_withdraw()
            elif choice == "3":
                self._handle_balance()
            elif choice == "4":
                self._handle_transactions()
            elif choice == "5":
                self._handle_settings()
            elif choice == "0":
                self._display_response("GOODBYE", "Thank you for using Mobile Money!")
                break
            else:
                print("❌ Invalid choice. Please enter 0-5")
    
    def run(self):
        """Main USSD client loop"""
        print("\n" + "="*35)
        print("  MOBILE MONEY USSD CLIENT")
        print("="*35)
        
        # Initialize session
        if not self._start_session():
            print("❌ Failed to start session. Make sure the server is running.")
            print(f"   Server URL: {self.server_url}")
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
        "--server",
        help="Server URL (default: http://localhost:8001)",
        type=str,
        default="http://localhost:8001"
    )
    
    args = parser.parse_args()
    
    # Create and run client
    client = USSDPhoneClient(
        phone_number=args.phone,
        server_url=args.server
    )
    client.run()


if __name__ == "__main__":
    main()
