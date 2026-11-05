import cloudinary
import cloudinary.api
import cloudinary.exceptions
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify the configured Cloudinary credentials with a signed ping (secret is never printed)."

    def handle(self, *args, **options):
        config = cloudinary.config()
        if not (config.cloud_name and config.api_key and config.api_secret):
            raise CommandError(
                "Cloudinary is not fully configured: set CLOUDINARY_URL "
                "(cloudinary://<api_key>:<api_secret>@<cloud_name>)."
            )

        try:
            cloudinary.api.ping()
        except cloudinary.exceptions.Error as exc:
            raise CommandError(f"Cloudinary rejected the credentials: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"OK (cloud_name={config.cloud_name})"))
