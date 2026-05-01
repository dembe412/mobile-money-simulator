"""
Client-side Remote Procedure Call (RPC) implementation
Allows clients to communicate with distributed servers
Includes server discovery, request signing, and automatic retry
"""
import requests
import json
import hmac
import hashlib
from typing import Dict, Optional, Tuple, List
from datetime import datetime
import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class ClientRPCError(Exception):
    """Custom exception for client RPC errors"""
    pass


class Request:
    """Helper class to build and sign requests"""
    
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.timestamp = datetime.utcnow().isoformat()
        self.payload: Dict = {}
    
    def add_param(self, key: str, value) -> "Request":
        """Add parameter to request"""
        self.payload[key] = value
        return self
    
    def sign(self, secret_key: str) -> str:
        """Generate HMAC signature for request"""
        message = f"{self.request_id}:{self.timestamp}:{json.dumps(self.payload, sort_keys=True)}"
        signature = hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature


class MobileMoneyClient:
    """
    Client library for interacting with Mobile Money System
    Handles server discovery, request routing, and RPC calls
    """
    
    def __init__(
        self,
        base_url: str = None,
        server_urls: Optional[List[str]] = None,
        api_key: str = "default-api-key",
        secret_key: str = "secret-key",
        timeout: int = 10
    ):
        """
        Initialize client
        
        Args:
            base_url: Single server URL (e.g., 'http://localhost:8001')
            server_urls: List of server URLs (e.g., ['http://localhost:8001', ...])
            api_key: API key for requests
            secret_key: Secret key for signing
            timeout: Request timeout in seconds
        """
        if base_url:
            self.server_urls = [base_url]
        else:
            self.server_urls = server_urls or [
                "http://localhost:8001",
                "http://localhost:8002",
                "http://localhost:8003"
            ]
        self.api_key = api_key
        self.secret_key = secret_key
        self.timeout = timeout
        self.current_server_idx = 0
    
    def _get_headers(self, request_id: str, signature: str) -> Dict:
        """Build request headers with authentication"""
        return {
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
            "X-API-Key": self.api_key,
            "X-Signature": signature,
            "User-Agent": "MobileMoneyClient/1.0"
        }
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        request_id: str = None,
        signature: str = None
    ) -> Tuple[bool, Dict]:
        """
        Make HTTP request to server with retry logic
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path
            data: Request data
            request_id: Request identifier
            signature: Request signature
            
        Returns:
            (success: bool, response: dict)
        """
        max_retries = 3
        last_error = None
        
        # Try each server
        for attempt in range(len(self.server_urls) * max_retries):
            server_idx = attempt % len(self.server_urls)
            server_url = self.server_urls[server_idx]
            
            try:
                url = urljoin(server_url, endpoint)
                headers = self._get_headers(request_id or "", signature or "")
                
                logger.debug(f"Request to {url} (attempt {attempt + 1})")
                
                if method.upper() == "GET":
                    response = requests.get(url, headers=headers, timeout=self.timeout)
                elif method.upper() == "POST":
                    response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
                else:
                    raise ClientRPCError(f"Unsupported method: {method}")
                
                if response.status_code in [200, 201]:
                    return True, response.json()
                
                elif response.status_code == 400:
                    return False, {
                        "status": "error",
                        "message": response.json().get("detail", "Bad request")
                    }
                
                elif response.status_code >= 500:
                    last_error = f"Server error: {response.status_code}"
                    self._rotate_server()
                
                else:
                    return False, response.json()
                    
            except requests.exceptions.ConnectTimeout:
                last_error = f"Connection timeout to {server_url}"
                self._rotate_server()
                
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                self._rotate_server()
            
            except Exception as e:
                last_error = str(e)
                logger.error(f"Request failed: {last_error}")
        
        return False, {
            "status": "error",
            "message": f"All servers failed. Last error: {last_error}"
        }
    
    def _rotate_server(self):
        """Rotate to next server"""
        self.current_server_idx = (self.current_server_idx + 1) % len(self.server_urls)
    
    def discover_server(self, phone_number: str) -> Dict:
        """
        Discover server for a phone number using consistent hashing
        All servers are equal - request routes to server determined by hash.
        
        Args:
            phone_number: Client phone number
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            success, response = self._make_request(
                "GET",
                f"/api/v1/routing/discover/{phone_number}"
            )
            
            if success:
                routing = response.get("routing", {})
                assigned_server = routing.get("assigned_server", {})
                failover_servers = routing.get("failover_servers", [])
                all_servers = routing.get("all_servers", [])
                
                # Build server list with assigned server first, then failover servers
                servers = []
                if assigned_server.get("url"):
                    servers.append(assigned_server.get("url"))
                
                # Add failover servers for automatic failover
                for server in failover_servers:
                    if server.get("url") and server.get("url") not in servers:
                        servers.append(server.get("url"))
                
                # Update client's server list for automatic failover
                if servers:
                    self.server_urls = servers
                    logger.info(f"Updated server list for {phone_number}: {servers}")
                
                return {
                    "success": True,
                    "message": "Server discovered",
                    "data": {
                        "server_id": assigned_server.get("id", "Unknown"),
                        "url": assigned_server.get("url"),
                        "assigned_server": assigned_server,
                        "failover_servers": failover_servers,
                        "all_servers": all_servers
                    }
                }
            
            return {
                "success": False,
                "message": response.get("detail", "Server discovery failed"),
                "data": response
            }
            
        except Exception as e:
            logger.error(f"Server discovery failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }
    
    def create_account(
        self,
        phone_number: str,
        account_holder_name: str = "User",
        initial_balance: float = 0.0
    ) -> Dict:
        """
        Create a new account
        
        Args:
            phone_number: Phone number
            account_holder_name: Account holder name
            initial_balance: Initial balance
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            request = Request(f"create_account_{phone_number}_{datetime.utcnow().timestamp()}")
            
            data = {
                "phone_number": phone_number,
                "account_holder_name": account_holder_name,
                "initial_balance": initial_balance
            }
            
            signature = request.add_param("phone_number", phone_number).sign(self.secret_key)
            
            success, response = self._make_request(
                "POST",
                "/api/v1/account/create",
                data,
                request.request_id,
                signature
            )
            
            if success:
                return {
                    "success": True,
                    "message": "Account created successfully",
                    "data": response.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Account creation failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"Account creation failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }
    
    def withdraw(
        self,
        account_id,
        phone_number: str,
        amount: float,
        client_reference: str = None
    ) -> Dict:
        """
        Withdraw funds from account
        
        Args:
            account_id: Account ID
            phone_number: Phone number
            amount: Amount to withdraw
            client_reference: Optional client reference
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            request = Request(f"withdraw_{account_id}_{amount}_{datetime.utcnow().timestamp()}")
            
            data = {
                "account_id": account_id,
                "phone_number": phone_number,
                "amount": amount,
                "client_ip": "0.0.0.0",
                "client_reference": client_reference
            }
            
            signature = request.add_param("amount", amount).sign(self.secret_key)
            
            success, response = self._make_request(
                "POST",
                "/api/v1/operation/withdraw",
                data,
                request.request_id,
                signature
            )
            
            if success:
                message = response.get("message", "Withdrawal request accepted")
                return {
                    "success": True,
                    "message": message,
                    "data": response.get("data", {}),
                    "request_id": response.get("request_id"),
                    "processing_status": response.get("processing_status"),
                    "check_status_url": response.get("check_status_url"),
                    "raw_response": response,
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Withdrawal failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"Withdrawal failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }
    
    def deposit(
        self,
        account_id,
        phone_number: str,
        amount: float,
        client_reference: str = None
    ) -> Dict:
        """
        Deposit funds to account
        
        Args:
            account_id: Account ID
            phone_number: Phone number
            amount: Amount to deposit
            client_reference: Optional client reference
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            request = Request(f"deposit_{account_id}_{amount}_{datetime.utcnow().timestamp()}")
            
            data = {
                "account_id": account_id,
                "phone_number": phone_number,
                "amount": amount,
                "client_ip": "0.0.0.0",
                "client_reference": client_reference
            }
            
            signature = request.add_param("amount", amount).sign(self.secret_key)
            
            success, response = self._make_request(
                "POST",
                "/api/v1/operation/deposit",
                data,
                request.request_id,
                signature
            )
            
            if success:
                message = response.get("message", "Deposit request accepted")
                return {
                    "success": True,
                    "message": message,
                    "data": response.get("data", {}),
                    "request_id": response.get("request_id"),
                    "processing_status": response.get("processing_status"),
                    "check_status_url": response.get("check_status_url"),
                    "raw_response": response,
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Deposit failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"Deposit failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }

    def get_operation_request_status(self, request_id: str) -> Dict:
        """Fetch async operation status by request ID."""
        try:
            success, response = self._make_request(
                "GET",
                f"/api/v1/operation/request/{request_id}",
            )

            if success:
                return {
                    "success": True,
                    "message": "Request status fetched",
                    "data": response,
                }

            return {
                "success": False,
                "message": response.get("message", "Failed to fetch request status"),
                "data": response,
            }
        except Exception as e:
            logger.error(f"Get request status failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {},
            }
    
    def check_balance(
        self,
        account_id,
        phone_number: str = None
    ) -> Dict:
        """
        Check account balance
        
        Args:
            account_id: Account ID
            phone_number: Phone number (optional)
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            request = Request(f"balance_{account_id}_{datetime.utcnow().timestamp()}")
            
            data = {
                "account_id": account_id,
                "phone_number": phone_number,
                "client_ip": "0.0.0.0"
            }
            
            signature = request.add_param("account_id", account_id).sign(self.secret_key)
            
            success, response = self._make_request(
                "POST",
                "/api/v1/operation/balance",
                data,
                request.request_id,
                signature
            )
            
            if success:
                return {
                    "success": True,
                    "message": "Balance retrieved",
                    "data": response.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Balance check failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"Balance check failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }
    
    def ussd_request(self, ussd_input: str, phone_number: str = None, session_id: str = None) -> Dict:
        """
        Send USSD request
        Format: *165*operation*phone*amount
        
        Args:
            ussd_input: USSD code string
            phone_number: Optional phone number
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            request = Request(f"ussd_{ussd_input}_{datetime.utcnow().timestamp()}")
            
            data = {
                "ussd_input": ussd_input,
                "phone_number": phone_number,
                "session_id": session_id,
                "client_ip": "0.0.0.0"
            }
            
            signature = request.add_param("ussd_input", ussd_input).sign(self.secret_key)
            
            success, response = self._make_request(
                "POST",
                "/api/v1/ussd",
                data,
                request.request_id,
                signature
            )
            
            if success:
                return {
                    "success": True,
                    "message": "USSD request processed",
                    "data": response.get("data", {}),
                    "session_id": response.get("session_id"),
                    "session_state": response.get("session_state"),
                    "session_active": response.get("session_active"),
                    "ussd_response": response.get("ussd_response"),
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "USSD request failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"USSD request failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }

    def start_ussd_session(self, phone_number: str) -> Dict:
        """Start a persistent USSD session for a phone number."""
        return self.ussd_request("*165#", phone_number=phone_number)

    def continue_ussd_session(self, session_id: str, user_input: str, phone_number: str = None) -> Dict:
        """Send a follow-up input to an existing USSD session."""
        return self.ussd_request(user_input, phone_number=phone_number, session_id=session_id)
    
    def get_transactions(self, account_id, limit: int = 10) -> Dict:
        """
        Get transaction history
        
        Args:
            account_id: Account ID
            limit: Number of transactions
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            success, response = self._make_request(
                "POST",
                "/api/v1/operation/transactions",
                {"account_id": account_id, "limit": limit}
            )
            
            if success:
                return {
                    "success": True,
                    "message": "Transactions retrieved",
                    "data": response.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Transaction retrieval failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"Transaction retrieval failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }
    
    def get_transaction_history(
        self,
        account_id,
        phone_number: str = None,
        limit: int = 10
    ) -> Dict:
        """Alias for get_transactions for backward compatibility"""
        return self.get_transactions(account_id, limit)
    
    def get_account_details(
        self,
        account_id,
        phone_number: str = None
    ) -> Dict:
        """
        Get account details
        
        Args:
            account_id: Account ID
            phone_number: Phone number (optional)
            
        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        try:
            success, response = self._make_request(
                "GET",
                f"/api/v1/account/{account_id}"
            )
            
            if success:
                return {
                    "success": True,
                    "message": "Account details retrieved",
                    "data": response.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": response.get("message", "Account retrieval failed"),
                    "data": {}
                }
        except Exception as e:
            logger.error(f"Account retrieval failed: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "data": {}
            }


# Example usage
if __name__ == "__main__":
    import time
    
    # Initialize client
    client = MobileMoneyClient(
        server_urls=[
            "http://localhost:8001",
            "http://localhost:8002",
            "http://localhost:8003"
        ]
    )
    
    print("=== Mobile Money Client Example ===\n")
    
    # 1. Create account
    print("1. Creating account...")
    result = client.create_account(
        "075346363",
        "John Doe",
        10000.0
    )
    success = result.get("success", False)
    print(f"   Status: {success}")
    print(f"   Response: {json.dumps(result, indent=2)}\n")

    if success:
        account_id = result.get("data", {}).get("account_id", 1)

        # 2. Check balance
        print("2. Checking balance...")
        result = client.check_balance(account_id)
        success = result.get("success", False)
        print(f"   Status: {success}")
        print(f"   Response: {json.dumps(result, indent=2)}\n")

        # 3. Withdraw
        print("3. Withdrawing 1000 KES...")
        result = client.withdraw(account_id, "075346363", 1000.0)
        success = result.get("success", False)
        print(f"   Status: {success}")
        print(f"   Response: {json.dumps(result, indent=2)}\n")

        # 4. Deposit
        print("4. Depositing 500 KES...")
        result = client.deposit(account_id, "075346363", 500.0)
        success = result.get("success", False)
        print(f"   Status: {success}")
        print(f"   Response: {json.dumps(result, indent=2)}\n")

        # 5. USSD withdraw
        print("5. USSD Withdraw (*165*2*075346363*1000)...")
        result = client.ussd_request("*165*2*075346363*1000#")
        success = result.get("success", False)
        print(f"   Status: {success}")
        print(f"   Response: {json.dumps(result, indent=2)}\n")

        # 6. USSD balance check
        print("6. USSD Balance Check (*165*3*075346363)...")
        result = client.ussd_request("*165*3*075346363#")
        success = result.get("success", False)
        print(f"   Status: {success}")
        print(f"   Response: {json.dumps(result, indent=2)}\n")
