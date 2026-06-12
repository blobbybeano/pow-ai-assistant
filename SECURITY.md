# Security and credentials

This repository does not include usable API keys, passwords, customer records,
Firebase service-account files, OAuth secrets, or provider account settings.

Create a local `.env` from `.env.example` and enter credentials for accounts you
control. Firebase users should run `flutterfire configure` for their own Firebase
project or provide the documented Dart defines. Never commit generated provider
configuration or service-account private keys.

If a credential is accidentally committed, revoke or rotate it at the provider
immediately. Removing it from Git history does not make the old credential safe.
