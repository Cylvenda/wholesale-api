# Shop Backend (Django)

A Django REST framework API for inventory management, sales, purchases, and accounting.

## Architecture

The project uses a modular app structure under `apps/`, with shared configuration in `config/`.

```
backend/
├── config/          # Project settings, shared models, URLs
├── apps/            # Business domain apps:
│   ├── accounts/    # Users, roles, authentication (JWT/Djoser)
│   ├── products/    # Products, brands, categories, units
│   ├── stock/       # Stock levels, movements, adjustments
│   ├── purchases/   # Purchase orders, suppliers
│   ├── sales/       # Sales orders, customers
│   ├── customers/   # Customer management
│   ├── suppliers/   # Supplier management
│   ├── expenses/    # Expense tracking, categories
│   ├── payments/    # Payment processing, methods
│   └── ...
├── manage.py
└── requirements.txt
```

## Tech Stack

- **Django 6.1** — web framework
- **DRF 3.18** — REST API
- **drf-spectacular** — OpenAPI schema generation
- **djangorestframework-simplejwt** — JWT authentication
- **djoser** — user registration/password management
- **psycopg** — PostgreSQL driver (SQLite supported for development)
- **django-cors-headers** — CORS handling
- **django-filter** — filtering backend

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL (recommended) or SQLite for development

### Installation

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate   # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your database and secret key configuration

# Run migrations
python manage.py migrate

# Create a superuser
python manage.py migrate --run-syncdb
```

### Development Server

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/`.

## API Endpoints

| Endpoint | Description |
|---|---|
| `/api/schema/` | OpenAPI schema (JSON/YAML) |
| `/api/docs/` | Swagger UI documentation |
| `/api/categories/` | Product categories CRUD |
| `/api/brands/` | Brands CRUD (filtered by category) |
| `/api/units/` | Measurement units CRUD |
| `/api/products/` | Products CRUD |
| `/api/stocks/` | Stock levels & movements |
| `/api/purchases/` | Purchase orders |
| `/api/sales/` | Sales orders |
| `/api/customers/` | Customer management |
| `/api/suppliers/` | Supplier management |
| `/api/expenses/` | Expense tracking |
| `/api/payments/` | Payment processing |

## Authentication

JWT-based authentication via Djoser:

```
POST /auth/jwt/create/      # Obtain token pair
POST /auth/jwt/refresh/     # Refresh access token
POST /auth/users/           # Register (admin)
POST /auth/users/me/        # Current user profile
```

## Testing

```bash
# Run all tests
python manage.py test

# Run tests for a specific app
python manage.py test apps.products
```

## Key Models

- **BaseModel** — abstract model with `uuid`, `created_by`, `created_at`, `updated_at`
- **Category** — product categories (name, description)
- **Brand** — brands with FK to Category
- **Unit** — measurement units (name, abbreviation, quantity)
- **Product** — products with brand, unit, pricing
- **Stock** — stock levels per product
- **Purchase/Sale** — order management with line items

## Database

The project includes `db.sqlite3` for local development. For production, use PostgreSQL by updating the `DATABASE_URL` in `.env`.
