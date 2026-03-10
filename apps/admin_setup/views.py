from django.http import HttpResponse
from django.core.management import call_command
from django.conf import settings

def run_setup(request):
    token = request.GET.get('token')
    
    if token != settings.ADMIN_SETUP_TOKEN:
        return HttpResponse('unauthorized', status=401)
    
    # create superuser
    call_command(
        'createsuperuser',
        interactive=False,
        username='admin',
        email='admin@gmail.com'
    )
    
    call_command('create_system_wallet')
    return HttpResponse('Setup complete')
