import pytest
import json
import socket
import ssl
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vm_manager.core.guest_client import VirtioSerialClient, CommandType, GuestAgentResponse

class TestGuestAgentProtocol:
    """Tests for Guest Agent framing and protocol."""

    @pytest.fixture(autouse=True)
    def mock_socket_constants(self):
        with patch("socket.AF_UNIX", create=True) as m1, \
             patch("socket.socket") as m2:
            yield m2

    @pytest.fixture
    def mock_ssl(self):
        with patch("ssl.create_default_context") as m:
            # Mock the context and wrap_socket
            context = MagicMock()
            m.return_value = context
            yield m, context

    def test_framing_and_send(self, mock_ssl):
        """Verify STX/ETX framing in sent messages."""
        m_ssl, context = mock_ssl
        client = VirtioSerialClient("/tmp/test.sock")
        
        # Manually set as connected with mocked socket
        client._socket = MagicMock()
        client._connected = True
        
        # Prepare response for the read that follows send
        response_data = {
            "success": True,
            "command": "ping",
            "data": {"status": "ok"}
        }
        response_json = json.dumps(response_data).encode('utf-8')
        client._socket.recv.return_value = b'\x02' + response_json + b'\x03'
        
        client.send_command(CommandType.PING)
        
        # Verify sent data has framing
        args, kwargs = client._socket.sendall.call_args
        sent_data = args[0]
        assert sent_data.startswith(b'\x02')
        assert sent_data.endswith(b'\x03')
        
        # Decode inner JSON
        inner_json = sent_data[1:-1].decode('utf-8')
        message = json.loads(inner_json)
        assert message["command"] == "ping"

    def test_message_receiving_fragments(self):
        """Verify receiving a message in multiple chunks."""
        client = VirtioSerialClient("/tmp/test.sock")
        client._socket = MagicMock()
        
        response_json = b'{"success": true}'
        # Return in 3 chunks: STX + part, part, part + ETX
        client._socket.recv.side_effect = [
            b'\x02{"succ',
            b'ess": tr',
            b'ue}\x03'
        ]
        
        result = client._recv_message()
        assert result == '{"success": true}'

    def test_tls_wrapping(self, mock_ssl):
        """Verify socket is wrapped with TLS upon connection."""
        m_ssl, context = mock_ssl
        
        # Mock cert exists
        with patch("pathlib.Path.exists", return_value=True):
            client = VirtioSerialClient("/tmp/test.sock")
            success = client.connect()
            
            assert success is True
            # Verify context creation and load_cert_chain
            m_ssl.assert_called_once()
            context.load_cert_chain.assert_called_once()
            # Verify wrap_socket was called
            context.wrap_socket.assert_called_once()
