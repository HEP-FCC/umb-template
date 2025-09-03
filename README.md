# Universal Metadata Browser Template

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Customizable and modularized, full-stack web application template for creating a searchable metadata catalog.

## 🌌 Example adaptations

- [Example of a configuration commit based on the docs/TUTORIAL.md](https://github.com/HEP-FCC/umb-bookstore-example/commit/264c5afe6173dc2e4d7e4db7a835f7c2d0c16d81)
- <https://fcc-physics-events.web.cern.ch>

## ✨ Features

### 🔍 **Advanced Search**

- Custom query language with field-specific operators
- Full-text search across all metadata
- Regex pattern matching and fuzzy search
- Search suggestions and autocomplete

### 📊 **Hierarchical Navigation**

- Configurable multi-level entity relationships
- Dynamic navigation menus based on your data structure
- URL-based bookmarkable searches

### 🪄 **Flexible UI**

- Adjustable display style for each type of metadata
- Currently supports numbers, strings and vectors
- Easily extandable for metadata new types
- Dynamically computed layout

### 📁 **Automated Data Management**

- File system monitoring with automatic import of new data
- Batch processing for large datasets
- JSON data format support with extensible import system

### 🔐 **Built-in Authentication**

- **Flexible Authentication**: Can be completely disabled for simple deployments or public data
- **CERN's Single Sign-On (SSO)**: Full OIDC integration for CERN environments
- **Role-based Access Control**: Configurable per-endpoint access control
- **Session Management**: Secure token handling with automatic refresh
- *Note: Currently optimized for CERN OIDC implementation, but code can be adapted for other OIDC providers*

## 🚀 Quick Start

### Prerequisites

- Docker or Podman (with Docker-Compose support for development)

### 1. Clone and Setup

```bash
git clone https://github.com/your-org/universal-metadata-browser-template.git universal-metadata-browser
cd universal-metadata-browser
# Edit the .env with your configuration
cp .env.example .env
# For dev edit also the .envfile with your configuration similar to the .env file
cp .envfile.example .envfile
```

### 2. Customize for Your Domain

Before starting the application, you need to:

- **Define your database schema** in `backend/app/storage/database.sql`
- **Implement your Pydantic data model** in `backend/app/storage/json_data_model.py`
- **Update the entity UUID computation function** in `backend/app/utils/uuid_utils.py`
- **Update configuration** primarily through environment variables in `.env` and `.envfile` (see tutorial for details)
- **Update frontend configuration** in `frontend/config/app.config.ts` (includes cookie name prefix for user preferences)
- **Customize contact information** in `frontend/components/ContactModal.vue` (change email, forum links, and repository URLs to match your organization)
- **(Optionally)** Update design colors in `frontend/assets/css/colors.css` and your logo at `frontend/public/logo.png`

> **💡 Configuration Note**: The backend is designed to be configured primarily through environment variables rather than editing the HOCON configuration files directly.

#### Schema Design Guidelines

**Entity Name Field Requirement**: Your Pydantic model must include a `name`. You can parse it from JSON field with other name, but in the Pydantic model and in the database schema it must be called `name`, at least for now. We can fairly easily add support other names defined in config if required later.

```sql
CREATE TABLE IF NOT EXISTS your_main_table (
    entity_id BIGSERIAL PRIMARY KEY,
    -- your other columns...
);

- **UUID Generation**: Creates deterministic UUIDs for conflict resolution
- **Display Names**: Used throughout the frontend for entity identification
- **Search Functionality**: Primary field used for entity name searches

**Navigation Order Configuration**: Update the navigation display order in `backend/app/config.conf` to match your data structure:

```hocon
# Navigation configuration - determines frontend menu order
navigation {
    order = ["category", "type", "source", "status", "format"]
}
```

**Important**: Navigation order values must match your foreign key column names **without the `_id` suffix**. For example, if your table has `publisher_id`, use `"publisher"` in the navigation order.

While the backend can handle custom primary key names (like `book_id`, `publication_id`), using `entity_id` eliminates potential configuration issues and makes your implementation more maintainable.

#### Frontend Cookie Configuration

The frontend uses cookies to store user preferences (search settings, metadata display preferences). Cookie names are configurable through the frontend configuration:

```typescript
// In frontend/config/app.config.ts
cookies: {
    namePrefix: "metadata" as const,  // Change this to match your domain
}
```

This will generate cookie names like `{namePrefix}-search-preferences` and `{namePrefix}-metadata-preferences`. This approach ensures that multiple deployments of the template on the same domain won't conflict with each other's user preferences.

#### Frontend Redirects Configuration

The template also includes a flexible redirect system for handling legacy URLs or migrating from existing websites. This is particularly useful when transitioning from an old site structure to the new metadata browser.

**Configuration File**: `frontend/config/redirects.json`

```json
{
    "redirects": {
        "/old/legacy-path.php": "/new/path",
        "/another/old/path": "/categories/books",
        "/removed-page": ""
    }
}
```

#### Required System Columns

Your main table **must include** these system columns for proper functionality:

```sql
-- Required system columns (automatically managed by the system)
name VARCHAR NOT NULL                                -- Primary entity identifier
uuid UUID PRIMARY KEY,                    -- Deterministic UUID for conflict resolution
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),  -- Auto-set on creation
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),  -- Auto-updated on changes
last_edited_at TIMESTAMP WITH TIME ZONE,            -- Manual edit tracking
edited_by_name VARCHAR,                              -- User who made manual edits
metadata JSONB,                                      -- Flexible storage for unmapped fields
title VARCHAR,                                       -- Display title (from metadata or name)
```

### 3. Configure Authentication (Optional)

The template supports two authentication modes:

#### **No Authentication (Default)**

Perfect for public data or simple internal deployments:

```bash
# In your .env file:
METADATA_BROWSER_AUTH_ENABLED="false"
```

When disabled, all API endpoints work without authentication and the frontend shows no login/logout UI.

#### **CERN SSO Authentication**

For secure deployments requiring user authentication:

```bash
# In your .env file:
METADATA_BROWSER_AUTH_ENABLED="true"
METADATA_BROWSER_CERN_CLIENT_ID="your-cern-client-id"
METADATA_BROWSER_CERN_CLIENT_SECRET="your-cern-client-secret"
METADATA_BROWSER_AUTH_OIDC_URL="https://auth.cern.ch/auth/realms/cern/.well-known/openid_configuration"
METADATA_BROWSER_AUTH_ISSUER="https://auth.cern.ch/auth/realms/cern"
METADATA_BROWSER_REQUIRED_CERN_ROLE="metadata-browser-user"
```

**Important**: When authentication is enabled, you also need a secure application secret:

```bash
METADATA_BROWSER_APPLICATION_SECRET_KEY="your-very-secure-random-key"
```

### 4. Start the Application

```bash
docker-compose up --build -d
```

### 5. Access the Application

- **Frontend**: <http://localhost:3000>
- **Backend API**: <http://localhost:8000>

> **💡 Authentication Note**: If you disabled authentication, you can immediately start using the application. If you enabled CERN SSO, users will need to authenticate before accessing protected endpoints.

## 🚢 Kubernetes Deployment with Kompose

If you prefer to deploy to Kubernetes instead of using Docker Compose, you can use [Kompose](https://kompose.io/) to automatically convert your Docker Compose files to Kubernetes manifests.

## 📖 Guide

Tutorial with specific example deployment can be found [here in the docs/ folder](docs/TUTORIAL.md).

## 🛠️ Template Adaptation Process

1. **📋 Plan Your Schema** - Define entities and relationships
2. **🗄️ Configure Database** - Set up tables and indexes
3. **📥 Implement Import** - Update data ingestion logic
4. **⚙️ Update Configuration** - Customize settings and branding
5. **🚀 Deploy** - Launch your customized portal

## 🤝 Contributing

We welcome contributions! Please see submit an issue or prepare a PR and we will happily discuss it with you.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/your-org/universal-metadata-browser-template.git universal-metadata-browser
cd universal-metadata-browser

# Start development environment
docker-compose up --build -d

# Install dependencies for local development (optional)
cd backend && uv sync
cd ../frontend && yarn install
```

### Code Checks

#### Backend (Python)

```bash
# Check code formatting and linting
cd backend
ruff check                    # Check for linting issues
ruff format --check           # Check formatting without making changes
ruff format                   # Auto-format code
```

#### Frontend (TypeScript/Vue)

```bash
# Check and fix linting and formatting
cd frontend
yarn lint --fix              # Check and auto-fix ESLint issues
yarn type-check              # TypeScript type checking
```

## 🙏 Acknowledgments

- Developed by [@lexi-k](https://github.com/lexi-k) during the CERN Summer Student Programme 2025
