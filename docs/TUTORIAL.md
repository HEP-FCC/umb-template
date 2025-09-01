# Tutorial: Building a Bookstore Metadata Browser

This tutorial walks you through adapting the Universal Metadata Browser Template to create a **Bookstore Metadata Briwser** - a complete example that demonstrates all the key concepts you'll need for your own domain.

## 🎯 What We're Building

By the end of this tutorial, you'll have a fully functional portal that can:

- Import book metadata from JSON files
- Search books by title, author, genre, and publisher
- Browse books by category, publisher, and publication year
- Display detailed book information with cover images and purchase links
- Support hierarchical navigation (publishers can have imprints, genres can have subgenres)

## 📋 Prerequisites

- Docker and Docker Compose installed
- Basic familiarity with Python and Vue.js
- A text editor or IDE

## 🚀 Tutorial Overview

1. [Setting Up Your Development Environment](#1-setting-up-your-development-environment)
2. [Designing Your Database Schema](#2-designing-your-database-schema)
3. [JSON Data Structure Requirements](#3-json-data-structure-requirements)
4. [Creating Data Models](#4-creating-data-models)
5. [Configuring Search and Navigation](#5-configuring-search-and-navigation)
6. [Customizing the Frontend](#6-customizing-the-frontend)
7. [Adding Sample Data](#7-adding-sample-data)
8. [Testing Your Portal](#8-testing-your-portal)

---

## 1. Setting Up Your Development Environment

### Step 1.1: Clone and Initialize

```bash
# Clone the template repository
git clone https://github.com/your-org/generic-metadata-portal.git bookstore-catalog
cd bookstore-catalog

# Copy environment configuration
cp .env.example .env
cp .envfile.example .envfile
```

### Step 1.2: Configure Environment Variables

Edit `.env` to customize for your bookstore:

```bash
# Database Configuration
METADATA_BROWSER_POSTGRES_HOST="localhost"
METADATA_BROWSER_POSTGRES_PORT=5432
METADATA_BROWSER_POSTGRES_USER="bookstore_admin"
METADATA_BROWSER_POSTGRES_PASSWORD="secure_password_here"
METADATA_BROWSER_POSTGRES_DB="bookstore_catalog"

# Application Configuration
METADATA_BROWSER_TITLE="Bookstore Catalog"
METADATA_BROWSER_DESCRIPTION="Discover and explore our book collection"
METADATA_BROWSER_SEARCH_PLACEHOLDER="Search books, authors, genres..."
METADATA_BROWSER_COOKIE_PREFIX="bookstore-catalog"

# File Watching Configuration
METADATA_BROWSER_FILE_WATCHER_PATHS="/data"
METADATA_BROWSER_FILE_WATCHER_EXTENSIONS=".json"
METADATA_BROWSER_STARTUP_MODE="process_all"

# Authentication (CERN-specific - see notes below)
METADATA_BROWSER_AUTH_ENABLED="false"  # Disable for development
# METADATA_BROWSER_CERN_CLIENT_ID="your-cern-client-id"
# METADATA_BROWSER_CERN_CLIENT_SECRET="your-cern-client-secret"
# METADATA_BROWSER_REQUIRED_CERN_ROLE="bookstore-admin"

# Logging
METADATA_BROWSER_LOG_LEVEL="INFO"
```

**Authentication Note**: This template is currently optimized for CERN's OIDC implementation. If you need to adapt it for other OIDC providers, you'll need to modify the authentication code in `backend/app/auth.py`. For development, you can disable authentication entirely by setting `METADATA_BROWSER_AUTH_ENABLED="false"`.

Edit `.envfile` with similar values (this is used by the frontend container).

### Step 1.3: Start Development Environment

```bash
# Build and start all services
docker-compose up --build -d

# Check that services are running
docker-compose ps
```

You should see:

- PostgreSQL database running on port 5432
- Backend API on port 8000
- Frontend development server on port 3000

---

## 2. Designing Your Database Schema

### Step 2.1: Define Your Entity Structure

The template uses a **dynamic schema discovery** approach. You define:

1. **Navigation tables** - lookup tables for categorical data (publishers, genres, etc.)
2. **Main table** - contains your core entities (books) with foreign keys to navigation tables

Replace the contents of `backend/app/storage/database.sql`:

```sql
F
```

### Step 2.2: Configure the Application

The template is designed to be configured primarily through **environment variables** rather than editing HOCON files directly. This makes deployment and customization easier across different environments.

Add the following environment variables to your `.env` file to configure the main table and navigation:

```bash
# Main table configuration (REQUIRED)
METADATA_BROWSER_MAIN_TABLE="books"

# Additional application settings
METADATA_BROWSER_TIMEOUT="30"
METADATA_BROWSER_DEFAULT_PAGE_SIZE="25"
METADATA_BROWSER_MAX_PAGE_SIZE="1000"
```

> **💡 Configuration Best Practice**: While you can edit `backend/app/config.conf` directly, using environment variables is recommended for easier deployment and environment-specific configuration. All HOCON settings support environment variable overrides using the `${?VARIABLE_NAME}` syntax.

```sql
-- Extensions for better search performance
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Navigation tables (lookup tables for categorical data)
CREATE TABLE IF NOT EXISTS research_fields (
    research_field_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS journals (
    journal_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS publication_types (
    publication_type_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS institutions (
    institution_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Main publications table
CREATE TABLE IF NOT EXISTS publications (
    entity_id BIGSERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),

    -- Core publication fields
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT[] NOT NULL,
    publication_date DATE,
    doi TEXT UNIQUE,
    pdf_url TEXT,
    keywords TEXT[],
    citation_count INTEGER DEFAULT 0,
    open_access BOOLEAN DEFAULT false,

    -- Foreign key relationships for navigation
    research_field_id INTEGER REFERENCES research_fields(research_field_id) ON DELETE SET NULL,
    journal_id INTEGER REFERENCES journals(journal_id) ON DELETE SET NULL,
    publication_type_id INTEGER REFERENCES publication_types(publication_type_id) ON DELETE SET NULL,
    institution_id INTEGER REFERENCES institutions(institution_id) ON DELETE SET NULL,

    -- Required fields for template framework
    name TEXT NOT NULL, -- Maps to title for search compatibility
    metadata JSONB, -- Store additional flexible data

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT chk_name_not_empty CHECK (length(trim(name)) > 0),
    CONSTRAINT chk_title_not_empty CHECK (length(trim(title)) > 0),
    CONSTRAINT chk_updated_at_after_created CHECK (updated_at >= created_at)
);

-- Search indexes for performance
CREATE INDEX IF NOT EXISTS idx_publications_title_gin ON publications USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_publications_abstract_gin ON publications USING GIN (abstract gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_publications_authors_gin ON publications USING GIN (authors);
CREATE INDEX IF NOT EXISTS idx_publications_keywords_gin ON publications USING GIN (keywords);
CREATE INDEX IF NOT EXISTS idx_publications_name_gin ON publications USING GIN (name gin_trgm_ops);

-- Foreign key indexes
CREATE INDEX IF NOT EXISTS idx_publications_research_field_id ON publications(research_field_id);
CREATE INDEX IF NOT EXISTS idx_publications_journal_id ON publications(journal_id);
CREATE INDEX IF NOT EXISTS idx_publications_publication_type_id ON publications(publication_type_id);
CREATE INDEX IF NOT EXISTS idx_publications_institution_id ON publications(institution_id);

-- Other useful indexes
CREATE INDEX IF NOT EXISTS idx_publications_doi ON publications(doi);
CREATE INDEX IF NOT EXISTS idx_publications_publication_date ON publications(publication_date);
CREATE INDEX IF NOT EXISTS idx_publications_created_at ON publications(created_at DESC);

-- Navigation table search indexes
CREATE INDEX IF NOT EXISTS idx_publishers_name_gin ON publishers USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_genres_name_gin ON genres USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_languages_name_gin ON languages USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_formats_name_gin ON formats USING GIN (name gin_trgm_ops);

-- Temporal indexes
CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at);
CREATE INDEX IF NOT EXISTS idx_books_updated_at ON books(updated_at);
CREATE INDEX IF NOT EXISTS idx_books_publication_date ON books(publication_date);
CREATE INDEX IF NOT EXISTS idx_books_created_at_desc ON books(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_books_updated_at_desc ON books(updated_at DESC);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_books_edited_id_composite ON books(last_edited_at DESC, entity_id);
CREATE INDEX IF NOT EXISTS idx_books_title_lower ON books(LOWER(title));

-- Performance optimization: Set statistics targets
ALTER TABLE books ALTER COLUMN name SET STATISTICS 1000;
ALTER TABLE books ALTER COLUMN title SET STATISTICS 1000;
ALTER TABLE books ALTER COLUMN authors SET STATISTICS 1000;
ALTER TABLE books ALTER COLUMN metadata SET STATISTICS 1000;
ALTER TABLE books ALTER COLUMN updated_at SET STATISTICS 500;

-- Set statistics for lookup tables
ALTER TABLE publishers ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE genres ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE languages ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE formats ALTER COLUMN name SET STATISTICS 100;
```

### Step 2.2: Schema Requirements and Best Practices

#### Required Fields for Template Compatibility

The template expects certain standard fields in your main table:

```sql
-- REQUIRED fields for all main tables:
entity_id BIGSERIAL PRIMARY KEY,               -- Primary key (recommended: always use 'entity_id')
uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(), -- Unique identifier for external APIs
name TEXT NOT NULL,                            -- Display name/title (used for search)
metadata JSONB,                               -- Flexible metadata storage
created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL, -- Creation timestamp
updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL, -- Last update timestamp

-- OPTIONAL fields for enhanced functionality:
last_edited_at TIMESTAMPTZ DEFAULT NULL,       -- Last manual edit timestamp
edited_by_name TEXT DEFAULT NULL,              -- Last editor name

-- Your domain-specific fields go here...
```

#### Schema Design Guidelines

- **Primary Key Naming**: **Always use `entity_id`** as your main table's primary key column name for maximum template compatibility
- **Entity Name Field**: **JSON data must include a `name` field** for each entity (configurable via `METADATA_BROWSER_ENTITY_NAME_FIELD`)
- **System Columns**: Certain database columns are treated as "system columns" and excluded from regular field mapping. The default system columns are: `entity_id`, `uuid`, `created_at`, `updated_at`, and the configured entity name field (by default `name`). This prevents conflicts during data import and ensures consistent behavior across all entity operations.
- **Navigation Tables**: Create lookup tables for categorical data (publishers, genres, etc.)
- **Foreign Keys**: Main table should reference navigation tables via `{table}_id` columns
- **Indexes**: Add GIN indexes for text search, BTREE for foreign keys
- **Constraints**: Include data validation constraints where appropriate

> **💡 Why `entity_id`?** The frontend expects `entity_id` as the primary key field. While the backend can handle custom primary key names, using `entity_id` eliminates configuration complexity and ensures all template features work seamlessly.
> **💡 Entity Name Field**: The `name` field in your JSON data serves as the primary identifier for UUID generation, display names, and search functionality. Without this field, entities will receive auto-generated fallback names.

#### UUID Function Customization

The template uses deterministic UUID generation to ensure data consistency. The UUID computation is based on the entity name and foreign key values. If your main table uses different field names, you may need to update the UUID computation logic.

**Key files to customize:**

1. **`backend/app/utils/uuid_utils.py`** - Contains the UUID generation function:

```python
# Update the namespace for your domain
ENTITY_UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_DNS,
    "your_domain.bookstore.v01"  # Replace with your domain
)

def generate_entity_uuid(
    entity_name: str,
    **foreign_key_ids: int | None,
) -> str:
    """Generate deterministic UUID for an entity based on identifying fields."""
    # This function works automatically with your foreign key names
    # e.g., publisher_id, genre_id, language_id, format_id
```

1. **Database service resolution logic** - The template automatically discovers your foreign key relationships and uses them for UUID computation. It expects:

   - Foreign key columns named `{table}_id` (e.g., `publisher_id`, `genre_id`)
   - Navigation tables with `name` columns for lookup
   - A `name` field in your main table for the entity identifier

**When to customize:**

- If you use different naming conventions for foreign keys
- If you need custom UUID generation logic for your domain
- If you want to change the UUID namespace for your application

### Step 2.3: Configure the Application

### Step 2.4: Apply the Schema

```bash
# Rebuild containers to apply schema changes
docker-compose down
docker-compose up --build -d

# Check that the database was created successfully
docker-compose logs postgres
```

---

## 3. JSON Data Structure Requirements

### Step 3.1: Required Fields

**Before creating data models**, ensure your JSON data includes these required fields:

#### Required Entity Fields

Every entity in your JSON data must include:

```json
{
  "name": "Entity Display Name",
  // ... other fields
}
```

- **`name` field**: Primary identifier used for entity display, search, and UUID generation
- Can be customized using `METADATA_BROWSER_ENTITY_NAME_FIELD` environment variable
- If missing, entities will receive auto-generated fallback names

#### System Columns Configuration

The system automatically excludes certain "system columns" from regular field mapping during data import to prevent conflicts:

**Default system columns:**

- `entity_id` - Primary key
- `uuid` - Unique identifier
- `created_at` - Record creation timestamp
- `updated_at` - Record modification timestamp
- Entity name field (default: `name`) - Configurable via `METADATA_BROWSER_ENTITY_NAME_FIELD`

**Customizing the entity name field:**

```bash
# In your .env file
METADATA_BROWSER_ENTITY_NAME_FIELD="title"  # Use "title" instead of "name"
```

This configuration ensures that your chosen field (e.g., `title`, `book_name`, `publication_title`) is treated as the primary entity identifier while being excluded from generic field processing.

#### Navigation Entity Fields

Include navigation entity names as direct fields:

```json
{
  "name": "Example Book",
  "publisher": "Penguin Random House",
  "genre": "Fiction",
  "language": "English",
  "format": "Hardcover",
  // ... other metadata
}
```

These fields will automatically create foreign key relationships in your database.

### Step 3.2: Example Book JSON Structure

```json
{
  "books": [
    {
      "name": "The Great Gatsby",
      "title": "The Great Gatsby",
      "authors": ["F. Scott Fitzgerald"],
      "isbn": "978-0-7432-7356-5",
      "publisher": "Scribner",
      "genre": "Fiction",
      "language": "English",
      "format": "Paperback",
      "publication_date": "1925-04-10",
      "pages": 180,
      "price": 14.99,
      "description": "A classic American novel..."
    }
  ]
}
```

Longer version:

```json
{
    "books": [
        {
            "title": "The Great Gatsby",
            "authors": [
                "F. Scott Fitzgerald"
            ],
            "isbn": "978-0-7432-7356-5",
            "publication_date": "1925-04-10",
            "pages": 180,
            "price": 14.99,
            "description": "A classic American novel about the Jazz Age and the American Dream.",
            "cover_image_url": "https://example.com/covers/great-gatsby.jpg",
            "purchase_url": "https://example.com/buy/great-gatsby",
            "publisher": "Penguin Random House",
            "genre": "Fiction",
            "language": "English",
            "format": "Paperback",
            "awards": [
                "Modern Library's Top 100"
            ],
            "theme": "American Dream"
        },
        {
            "title": "To Kill a Mockingbird",
            "authors": [
                "Harper Lee"
            ],
            "isbn": "978-0-06-112008-4",
            "publication_date": "1960-07-11",
            "pages": 281,
            "price": 16.99,
            "description": "A gripping tale of racial injustice and childhood innocence in the American South.",
            "cover_image_url": "https://example.com/covers/mockingbird.jpg",
            "purchase_url": "https://example.com/buy/mockingbird",
            "publisher": "HarperCollins",
            "genre": "Fiction",
            "language": "English",
            "format": "Hardcover",
            "awards": [
                "Pulitzer Prize for Fiction"
            ],
            "setting": "Alabama, 1930s"
        },
        {
            "title": "Dune",
            "authors": [
                "Frank Herbert"
            ],
            "isbn": "978-0-441-17271-9",
            "publication_date": "1965-06-01",
            "pages": 688,
            "price": 18.99,
            "description": "Epic science fiction novel set on the desert planet Arrakis.",
            "cover_image_url": "https://example.com/covers/dune.jpg",
            "purchase_url": "https://example.com/buy/dune",
            "publisher": "Macmillan",
            "genre": "Science Fiction",
            "language": "English",
            "format": "Paperback",
            "awards": [
                "Hugo Award",
                "Nebula Award"
            ],
            "series": "Dune Chronicles"
        },
        {
            "title": "Sapiens: A Brief History of Humankind",
            "authors": [
                "Yuval Noah Harari"
            ],
            "isbn": "978-0-06-231609-7",
            "publication_date": "2014-09-04",
            "pages": 443,
            "price": 19.99,
            "description": "An exploration of how Homo sapiens came to dominate the world.",
            "cover_image_url": "https://example.com/covers/sapiens.jpg",
            "purchase_url": "https://example.com/buy/sapiens",
            "publisher": "HarperCollins",
            "genre": "Non-Fiction",
            "language": "English",
            "format": "Hardcover",
            "category": "History/Anthropology",
            "bestseller": true
        },
        {
            "title": "1984",
            "authors": [
                "George Orwell"
            ],
            "isbn": "978-0-452-28423-4",
            "publication_date": "1949-06-08",
            "pages": 328,
            "price": 13.99,
            "description": "A dystopian social science fiction novel about totalitarian control.",
            "cover_image_url": "https://example.com/covers/1984.jpg",
            "purchase_url": "https://example.com/buy/1984",
            "publisher": "Penguin Random House",
            "genre": "Fiction",
            "language": "English",
            "format": "Paperback",
            "theme": "Dystopia",
            "setting": "Oceania, 1984"
        },
        {
            "title": "Pride and Prejudice",
            "authors": [
                "Jane Austen"
            ],
            "isbn": "978-0-14-143951-8",
            "publication_date": "1813-01-28",
            "pages": 432,
            "price": 12.99,
            "description": "A romantic novel that deals with issues of manners, upbringing, morality, education, and marriage.",
            "cover_image_url": "https://example.com/covers/pride-prejudice.jpg",
            "purchase_url": "https://example.com/buy/pride-prejudice",
            "publisher": "Penguin Classics",
            "genre": "Romance",
            "language": "English",
            "format": "Paperback",
            "theme": "Love and Marriage",
            "setting": "Rural England"
        }
    ]
}
```

---

## 4. Creating Data Models

### Step 4.1: Replace the FCC Data Models

The template includes FCC-specific data models that need to be replaced with your bookstore models. Replace the entire content of `backend/app/storage/json_data_model.py` with book-specific models:

**Key changes needed:**

1. Replace `FccDataset` class with `Book` class
2. Replace `DatasetCollection` with `BookCollection`
3. Update field names and validation logic
4. Update detection function to recognize book JSON format

Since this is a large code file, the key sections to understand are:

- `Book` class: Defines fields like `title`, `authors`, `isbn`, `price`, etc.
- Navigation fields: `publisher`, `genre`, `language`, `format` map to foreign keys
- `get_all_metadata()` method: Returns data for the JSONB metadata field
- Detection function: Identifies book collection JSON format
- Registry: Auto-registers the classes with the template system

---

## 5. Configuring Search and Navigation

The template automatically discovers your schema and builds navigation menus from foreign key relationships.

### Step 4.1: Update Frontend Configuration

Edit `frontend/config/app.config.ts` to customize for your bookstore:

```typescript
export const APP_CONFIG = {
    mainTable: "books" as const,

    branding: {
        title: "Bookstore Catalog",
        appTitle: "Bookstore Catalog Portal",
        description: "Discover and explore our book collection",
        defaultTitle: "Book Search",
    },

    metadata: {
        defaultSelectedFields: ["authors", "isbn", "pages", "price"] as const,
    },

    downloads: {
        fileNamePrefix: "bookstore_catalog" as const,
    },

    navigationFallback: {
        order: ["publisher", "genre", "language", "format"] as const,
    },
} as const;
```

### Step 5.2: Configure Navigation Order in Backend

The backend determines the display order of navigation menus through the `navigation.order` setting in `backend/app/config.conf`. Update this to match your data structure:

```hocon
# Navigation configuration
# Defines the order of navigation entities (determines display order in frontend)
# NOTE: These must match the foreign key column names in the main table (without _id suffix)
navigation {
    order = ["publisher", "genre", "language", "format"]
}
```

**Important**: The navigation order values must match your foreign key column names **without the `_id` suffix**:

- If your table has `publisher_id` column → use `"publisher"` in navigation order
- If your table has `genre_id` column → use `"genre"` in navigation order
- If your table has `language_id` column → use `"language"` in navigation order

This configuration ensures that navigation menus appear in your preferred order and properly reference the correct database relationships.

---

## 6. Customizing the Frontend

### Step 5.1: Update Application Branding

Update the logo alt text in `frontend/app.vue`:

```vue
<NuxtImg src="/logo.png" alt="Bookstore Catalog" class="h-8 w-auto" />
```

Optionally replace `frontend/public/logo.png` with your bookstore's logo.

The color system is designed to be easily customizable by editing values in `frontend/assets/css/colors.css` while keeping the same CSS variable names.

---

## 7. Adding Sample Data

### Step 6.1: Create Sample Book Data

Create your data directory and sample file:

```bash
mkdir -p backend/app/storage/data
```

Create `backend/app/storage/data/sample_books.json`:

```json
{
  "books": [
    {
      "title": "The Great Gatsby",
      "authors": ["F. Scott Fitzgerald"],
      "isbn": "978-0-7432-7356-5",
      "publication_date": "1925-04-10",
      "pages": 180,
      "price": 14.99,
      "description": "A classic American novel about the Jazz Age and the American Dream.",
      "cover_image_url": "https://example.com/covers/great-gatsby.jpg",
      "purchase_url": "https://example.com/buy/great-gatsby",
      "publisher": "Penguin Random House",
      "genre": "Fiction",
      "language": "English",
      "format": "Paperback",
      "awards": ["Modern Library's Top 100"],
      "theme": "American Dream"
    },
    {
      "title": "To Kill a Mockingbird",
      "authors": ["Harper Lee"],
      "isbn": "978-0-06-112008-4",
      "publication_date": "1960-07-11",
      "pages": 281,
      "price": 16.99,
      "description": "A gripping tale of racial injustice and childhood innocence in the American South.",
      "cover_image_url": "https://example.com/covers/mockingbird.jpg",
      "purchase_url": "https://example.com/buy/mockingbird",
      "publisher": "HarperCollins",
      "genre": "Fiction",
      "language": "English",
      "format": "Hardcover",
      "awards": ["Pulitzer Prize for Fiction"],
      "setting": "Alabama, 1930s"
    },
    {
      "title": "Dune",
      "authors": ["Frank Herbert"],
      "isbn": "978-0-441-17271-9",
      "publication_date": "1965-06-01",
      "pages": 688,
      "price": 18.99,
      "description": "Epic science fiction novel set on the desert planet Arrakis.",
      "cover_image_url": "https://example.com/covers/dune.jpg",
      "purchase_url": "https://example.com/buy/dune",
      "publisher": "Macmillan",
      "genre": "Science Fiction",
      "language": "English",
      "format": "Paperback",
      "awards": ["Hugo Award", "Nebula Award"],
      "series": "Dune Chronicles"
    },
    {
      "title": "Sapiens: A Brief History of Humankind",
      "authors": ["Yuval Noah Harari"],
      "isbn": "978-0-06-231609-7",
      "publication_date": "2014-09-04",
      "pages": 443,
      "price": 19.99,
      "description": "An exploration of how Homo sapiens came to dominate the world.",
      "cover_image_url": "https://example.com/covers/sapiens.jpg",
      "purchase_url": "https://example.com/buy/sapiens",
      "publisher": "HarperCollins",
      "genre": "Non-Fiction",
      "language": "English",
      "format": "Hardcover",
      "category": "History/Anthropology",
      "bestseller": true
    }
  ]
}
```

---

## 8. Testing Your Portal

### Step 7.1: Start Your Application

```bash
# Make sure you're in the project root directory
docker-compose up --build -d

# Check logs to see if everything is working
docker-compose logs -f backend
```

You should see logs indicating:

- Database connection successful
- Schema applied successfully
- File watcher starting
- JSON file detected and imported

### Step 7.2: Test the Frontend

1. **Access the Portal**: Go to `http://localhost:3000`

2. **Test Search**:
   - Try searching for: `Gatsby`, `Harari`, `science fiction`
   - Test field-specific searches: `title:Dune`, `author:Harari`, `genre:Fiction`

3. **Test Navigation**:
   - Browse by Publisher in the sidebar
   - Filter by Genre
   - Check that book counts are accurate

4. **Test Data Display**:
   - Verify book cards display correctly
   - Check that metadata shows properly

### Step 7.3: Add More Data

Test the file watcher by creating another JSON file:

```bash
cat > backend/app/storage/data/more_books.json << 'EOF'
{
  "books": [
    {
      "title": "1984",
      "authors": ["George Orwell"],
      "isbn": "978-0-452-28423-4",
      "publication_date": "1949-06-08",
      "pages": 328,
      "price": 13.99,
      "description": "A dystopian social science fiction novel about totalitarian control.",
      "publisher": "Penguin Random House",
      "genre": "Fiction",
      "language": "English",
      "format": "Paperback"
    }
  ]
}
EOF
```

Watch the logs to see automatic import:

```bash
docker-compose logs -f backend
```

### Step 7.4: Test the API Directly

Test the backend API:

```bash
# Get all books
curl "http://localhost:8000/entities?limit=10"

# Search for books
curl "http://localhost:8000/entities?q=Orwell"

# Get navigation counts
curl "http://localhost:8000/navigation"

# Get schema information
curl "http://localhost:8000/schema"
```

---

## 🎉 Congratulations

You've successfully created a Bookstore Catalog Portal! Your system can now:

✅ Import book metadata from JSON files
✅ Provide advanced search capabilities
✅ Display books with rich metadata
✅ Support hierarchical navigation by publisher, genre, etc.
✅ Auto-discover and adapt to your database schema
✅ Scale to handle thousands of books

## 🔄 Next Steps

Now that you have a working bookstore portal, consider:

1. **Adding More Data**: Import larger datasets, connect to book APIs
2. **Enhanced Search**: Add price ranges, publication date filters, advanced metadata search
3. **User Features**: Wishlists, reviews, ratings, user accounts
4. **Integration**: Connect to inventory systems, payment processors
5. **Advanced Features**: Recommendations, related books, author pages

## 📚 Key Concepts You've Learned

- **Dynamic Schema Discovery**: The template automatically detects your database structure
- **Navigation Entity Pattern**: Foreign key relationships become navigation menus
- **Pydantic Data Models**: Type-safe data validation and parsing
- **Metadata Flexibility**: Core fields + flexible JSONB metadata storage
- **File Watching**: Automatic data import from watched directories
- **Configuration-Driven**: Most customization through config files

## 🛠️ Adapting for Your Domain

To adapt this template for a different domain (e.g., product catalog, research papers, music library):

1. **Replace the database schema** with your entities and relationships
2. **Update the Pydantic models** to match your data structure
3. **Modify the configuration** for your branding and navigation
4. **Optionally customize** colors, icons, and UI elements

The core template handles all the complex functionality (search, navigation, data import, etc.) automatically!

## 🔐 Authentication Notes

This template is currently optimized for **CERN's OIDC implementation** and includes:

- CERN-specific role requirements
- CERN OAuth client configuration
- CERN-specific endpoints and validation

**To adapt for other OIDC providers:**

- Modify authentication code in `backend/app/auth.py`
- Update OIDC configuration endpoints
- Adjust role validation logic
- Update frontend authentication flows

**For development**, you can disable authentication entirely by setting `METADATA_BROWSER_AUTH_ENABLED="false"` in your environment.

## 🆘 Troubleshooting

**Problem**: File watcher not importing data

- Check file permissions on the data directory
- Verify JSON format is valid
- Check backend logs for error messages

**Problem**: Navigation not showing

- Verify foreign key relationships in your schema
- Check that navigation table names match your config
- Ensure sample data references valid navigation entities

**Problem**: Search not working

- Check database indexes were created
- Verify the main table name in config matches your schema
- Test API endpoints directly with curl

**Problem**: Configuration not taking effect

- Remember to use environment variables (`.env` and `.envfile`) instead of editing HOCON files directly
- Restart containers after changing environment variables: `docker-compose restart`
- Check that environment variable names match the expected format: `METADATA_BROWSER_*`
- Verify both `.env` (backend) and `.envfile` (frontend) are updated consistently

**Problem**: Frontend not connecting to backend

- Verify both containers are running: `docker-compose ps`
- Check network connectivity between containers
- Verify environment variables are set correctly

---

**Need Help?** Check out the [GitHub Issues](https://github.com/your-org/generic-metadata-portal/issues) for community support and examples.
