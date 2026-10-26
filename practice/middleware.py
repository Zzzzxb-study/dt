from django.contrib.auth import logout
from django.shortcuts import redirect
from .models import Profile


class AccountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile, created = Profile.objects.get_or_create(user=request.user, defaults={'must_change_password': not request.user.is_superuser})
            # Missing versions are only tolerated for newly created profiles.
            version = request.session.get('account_version')
            if version != profile.session_version:
                logout(request)
                return redirect('login')
            if profile.must_change_password and request.path not in ('/password/', '/logout/') and not request.path.startswith('/static/'):
                return redirect('password')
        response = self.get_response(request)
        if request.user.is_authenticated or request.path == '/login/':
            response['Cache-Control'] = 'no-store, private'
            response['Pragma'] = 'no-cache'
        return response
