# Secure Access System

A Windows-based secure access lockscreen application built with Python and Tkinter. This system provides authentication, session management, and system monitoring capabilities.

## Features

- **User Authentication**: Secure login system with credential management
- **Session Locking**: Lock/unlock system access with automatic timeout
- **Inactivity Detection**: Monitors system idle time and automatically locks inactive sessions
- **Keyboard Monitoring**: Low-level keyboard hook integration for system-wide monitoring
- **Web Service Integration**: SOAP-based communication with corporate services
- **Modern UI**: Dark-themed interface with color-coded status indicators
- **Activity Logging**: Tracks user actions and system events

## Requirements

- Python 3.7+
- Windows OS (uses Windows-specific APIs)
- Required Python packages:
  - tkinter (usually included with Python)
  - requests
  - ctypes (standard library)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install requests
   ```

## Configuration

### Files

- **users.txt**: List of authorized users
- **credential.txt**: Stores server path and connection details
- **lockapp.py**: Main application file


## Usage

Run the application:
```bash
python lockapp.py
```

The application will:
1. Load user credentials from configuration files
2. Display the login interface
3. Monitor for inactivity and user input
4. Manage system locking/unlocking based on authentication

## Build

The project includes a pre-built executable in the `build/SecureAccess/` directory, created with PyInstaller.

## Technical Details

### Keyboard Hook
- Implements low-level Windows keyboard hook (WH_KEYBOARD_LL)
- Operates even when input is blocked (BlockInput)
- Runs in a separate thread for non-blocking operation

### Inactivity Monitoring
- Polls system idle time every second
- Triggers lockout on inactivity timeout
- Shows countdown warning before lock

### Color Scheme
- Dark GitHub-inspired theme with accent colors
- Status indicators: Blue (info), Green (success), Red (danger), Yellow (warning)

## Security Notes

- Credentials are stored locally - ensure files have appropriate permissions
- System uses Windows API integration for security operations
- Keyboard monitoring requires elevated privileges on some systems

## License

Proprietary - Internal Use Only

## Support

For issues or questions, contact your system administrator.
