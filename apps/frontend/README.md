# GoLive - Mobile Frontend

React Native / Expo mobile application for GoLive panic button system.

## Environment Configuration

This app uses environment-specific configuration files to manage different deployment environments (development, staging, production).

### Environment Files

- `env.development` - Development environment (local backend at localhost:3000)
- `env.staging` - Staging environment
- `env.production` - Production environment
- `.env` - Active environment file (git-ignored)

### Available Scripts

```bash
# Development (uses env.development)
yarn start:dev

# Staging (uses env.staging)
yarn start:staging

# Production (uses env.production)
yarn start:prod

# Default start (uses current .env)
yarn start

# Platform-specific
yarn ios
yarn android
yarn web
```

### Environment Variables

Each environment file contains:

```
BASE_URL=http://localhost:3000/api/v1/mobile
WS_URL=ws://localhost:3000/cable
NODE_ENV=development
API_TIMEOUT=10000
DEBUG=true
```

### Setup

1. Install dependencies:
   ```bash
   yarn install
   ```

2. Start development server:
   ```bash
   yarn start:dev
   ```

3. Run on your preferred platform:
   ```bash
   # iOS
   yarn ios

   # Android
   yarn android

   # Web
   yarn web
   ```

### Android Emulator Note

When using the Android emulator, localhost URLs are automatically converted to `10.0.2.2` in the platform configuration.

### Features

- **Authentication**: JWT-based authentication with AsyncStorage
- **Environment Management**: Multi-environment support (dev/staging/prod)
- **Navigation**: React Navigation with stack navigator
- **Auto-logout**: Handles invalid tokens and 401 responses
- **API Service**: Centralized API client with timeout handling

### Project Structure

```
frontend/
├── App.js                  # Root component with navigation
├── app.config.js           # Expo configuration with env vars
├── babel.config.js         # Babel configuration
├── contexts/
│   └── AuthContext.js      # Authentication state management
├── screens/
│   ├── LoginScreen.js      # Login screen
│   └── HomeScreen.js       # Home screen (authenticated)
├── services/
│   └── apiService.js       # API client
├── utils/
│   ├── environment.js      # Environment utility
│   └── platformConfig.js   # Platform-specific config
├── env.development         # Dev environment config
├── env.staging             # Staging environment config
└── env.production          # Production environment config
```

## Authentication Flow

1. User enters email and password on LoginScreen
2. App sends POST request to `/api/v1/mobile/login`
3. On success, stores JWT token and user data in AsyncStorage
4. API requests include `Authorization: Bearer <token>` header
5. On 401 responses, triggers auto-logout

## Development

The app automatically shows environment configuration in debug mode on the login screen, making it easy to verify which backend you're connected to.
