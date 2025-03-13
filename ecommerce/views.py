from django.http import JsonResponse
from django.shortcuts import render
from django.core.mail import send_mail
from django.conf import settings

def landing_page(request):
    return render(request, 'index.html')

def send_query_email(request):
    if request.method == "POST":
        email = request.POST.get('email')
        message = request.POST.get('message')

        if email and message:
            try:
                subject = "New Query from Hardware Store"
                body = f"Email: {email}\n\nMessage:\n{message}"
                sender_email = settings.EMAIL_HOST_USER  
                recipient_email = settings.EMAIL_HOST_USER  

                send_mail(subject, body, sender_email, [recipient_email])

                return JsonResponse({"success": True, "message": "Email sent successfully!"})
            except Exception as e:
                return JsonResponse({"success": False, "error": str(e)}, status=500)
        
        return JsonResponse({"success": False, "error": "Missing email or message"}, status=400)

    return JsonResponse({"success": False, "error": "Invalid request method"}, status=405)

def terms_and_conditions(request):
    return render(request, 'terms_and_conditions.html')

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def cancellation_and_refunds(request):
    return render(request, 'cancellation_and_refunds.html')

def shipping_policy(request):
    return render(request, 'shipping_policy.html')

