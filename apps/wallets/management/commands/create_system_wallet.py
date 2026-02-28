"""
Management command to create the system wallet.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.wallets.models import Wallet

class Command(BaseCommand):
    help = 'Create the system wallet if it does not exist'
    
    def handle(self, *args, **options):
        wallet, created = Wallet.objects.get_or_create(
            is_system=True,
            currency=settings.WALLET_CURRENCY,
            defaults={
                'name': settings.SYSTEM_WALLET_NAME
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created system wallet: {wallet.id}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'System wallet already exists: {wallet.id}')
            )