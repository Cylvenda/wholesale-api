#!/usr/bin/env python
"""
Deployment script: creates a superuser on first run.

Run after migrations during deployment:

    python manage.py migrate
    python create_superuser.py

Environment variables (all optional with defaults shown):
    DJANGO_SUPERUSER_EMAIL     – admin@example.com
    DJANGO_SUPERUSER_PASSWORD  – changeme
    DJANGO_SUPERUSER_FIRST_NAME – Admin
    DJANGO_SUPERUSER_LAST_NAME  – User
    DJANGO_SUPERUSER_PHONE     – +255000000000

If a user with the same email already exists, no action is taken
and the script exits cleanly (safe to re-run during deployments).
"""

import os
import sys

import django
from django.contrib.auth import get_user_model

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

User = get_user_model()

email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "changeme")
first_name = os.environ.get("DJANGO_SUPERUSER_FIRST_NAME", "Admin")
last_name = os.environ.get("DJANGO_SUPERUSER_LAST_NAME", "User")
phone = os.environ.get("DJANGO_SUPERUSER_PHONE", "+255000000000")

existing = User.objects.filter(email=email).first()
if existing:
    print(f"Superuser already exists: {email}")
    sys.exit(0)

existing_phone_user = User.objects.filter(phone=phone).first()
if existing_phone_user:
    existing_phone_user.email = email
    existing_phone_user.first_name = first_name
    existing_phone_user.last_name = last_name
    existing_phone_user.role = User.Roles.ADMIN
    existing_phone_user.is_active = True
    existing_phone_user.is_staff = True
    existing_phone_user.is_superuser = True
    existing_phone_user.set_password(password)
    existing_phone_user.save(
        update_fields=[
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "password",
        ]
    )
    print(f"Superuser created (updated from existing phone): {email}")
    sys.exit(0)

user = User.objects.create_user(
    email=email,
    password=password,
    first_name=first_name,
    last_name=last_name,
    phone=phone,
    role=User.Roles.ADMIN,
    is_active=True,
    is_staff=True,
    is_superuser=True,
)
print(f"Superuser created: {email}")
