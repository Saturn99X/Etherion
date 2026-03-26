# src/utils/secure_string.py
import ctypes
import os
import threading
from typing import Optional


class SecureString:
    """
    A class for securely handling sensitive string data with automatic memory wiping.
    Implements context manager protocol for automatic cleanup.
    """
    
    def __init__(self, value: Optional[str] = None):
        """
        Initialize a SecureString with an optional value.
        
        Args:
            value: The string value to store securely
        """
        # Use RLock to avoid deadlocks when internal methods re-enter locking
        # e.g., _set_value() calls _clear_value() while holding the lock.
        self._lock = threading.RLock()
        self._value = None
        self._buffer = None
        self._length = 0
        
        if value is not None:
            self._set_value(value)
    
    def _set_value(self, value: str) -> None:
        """Set the value of the secure string."""
        with self._lock:
            # Clear any existing value
            self._clear_value()
            
            # Store the length
            self._length = len(value)
            
            # Allocate memory buffer
            self._buffer = ctypes.create_string_buffer(value.encode('utf-8'), self._length + 1)
            self._value = self._buffer.raw[:self._length].decode('utf-8')
    
    def _clear_value(self) -> None:
        """Clear the value and wipe memory."""
        with self._lock:
            if self._buffer is not None:
                # Wipe the memory buffer
                ctypes.memset(self._buffer, 0, self._length + 1)
                self._buffer = None
                self._value = None
                self._length = 0
    
    def get_value(self) -> Optional[str]:
        """Get the value of the secure string."""
        with self._lock:
            return self._value if self._value is not None else None
    
    def set_value(self, value: str) -> None:
        """Set the value of the secure string."""
        self._set_value(value)
    
    def clear(self) -> None:
        """Clear the value and wipe memory."""
        self._clear_value()
    
    def is_empty(self) -> bool:
        """Check if the secure string is empty."""
        with self._lock:
            return self._value is None or self._length == 0
    
    def __len__(self) -> int:
        """Return the length of the secure string."""
        with self._lock:
            return self._length
    
    def __str__(self) -> str:
        """Return a masked representation of the string."""
        return "[SECURE STRING]"
    
    def __repr__(self) -> str:
        """Return a masked representation of the string."""
        return f"SecureString(length={self._length})"
    
    # Context manager methods
    def __enter__(self):
        """Enter the context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and clear the value."""
        self.clear()
    
    # Destructor to ensure memory is wiped
    def __del__(self):
        """Destructor to ensure memory is wiped when object is deleted."""
        try:
            self.clear()
        except:
            # Ignore any errors during destruction
            pass