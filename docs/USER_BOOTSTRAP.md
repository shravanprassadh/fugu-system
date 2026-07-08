# Initial user bootstrap

Fugu has no default username or password. Authentication is database-backed, and passwords are stored only as Argon2 hashes.

Use the packaged `fugu-create-user` command after the database migrations have reached the current Alembic head.

## Required runtime configuration

Run the command in the same backend environment used by the application so these values are available:

- `MASTER_ROUTER_DB_URL`
- `METADATA_SIDEBAR_DB_URL`
- `TRANSACTIONAL_LOGS_DB_URL`
- `SYSTEM_SESSION_SECRET`
- `VAULT_ENCRYPTION_KEY`
- `ALLOWED_ORIGINS`

The account itself is stored only in the master database.

## Create the initial administrator

Inside the deployed backend container or virtual environment, run:

```bash
fugu-create-user --username admin --role admin
```

The command prompts twice for the password without echoing it. Passwords are never accepted through command-line arguments or environment variables, which prevents accidental exposure through shell history, process listings, deployment manifests, or logs.

The username must contain between 3 and 255 characters. The password must contain between 8 and 1024 characters and cannot consist only of whitespace.

For Docker:

```bash
docker exec -it <backend-container-name> fugu-create-user --username admin --role admin
```

For a non-administrator account:

```bash
fugu-create-user --username <username> --role user
```

The command refuses to overwrite an existing username.

## Authenticate

Use the selected username and password in the Studio login screen, or call the API directly:

```bash
curl --fail-with-body \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"username":"admin","password":"<your-password>"}' \
  https://<api-host>/api/auth/login
```

A successful response contains a short-lived bearer token. Do not store that token in source control or long-lived deployment configuration.

## Operational guidance

- Create the first account only after migrations complete successfully.
- Use a unique, high-entropy administrator password.
- Create separate named accounts for operators instead of sharing one credential.
- Do not insert plaintext passwords with SQL.
- Do not commit generated password hashes as fixtures or deployment defaults.
- Logout revokes all outstanding tokens for that user by incrementing `users.token_version`.
