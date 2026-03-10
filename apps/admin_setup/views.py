from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management import call_command


def run_setup(request):
    token = request.GET.get("token")
    if token != settings.ADMIN_SETUP_TOKEN:
        return HttpResponse("Unauthorized", status=401)

    User = get_user_model()

    email = "admin@example.com"
    password = settings.DJANGO_SUPERUSER_PASSWORD

    # Create superuser safely
    if not User.objects.filter(email=email).exists():
        user = User.objects.create(
            email=email,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        user.set_password(password)
        user.save()

    # Run your wallet bootstrap command
    call_command("create_system_wallet")

    return HttpResponse("SETUP COMPLETE")