from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib import messages
from django.http import JsonResponse

def landing_page(request):
    return render(request, 'index.html')  # Load the HTML file

def send_query_email(request):
    if request.method == "POST":
        email = request.POST.get('email')
        message = request.POST.get('message')

        if email and message:
            subject = "New Query from Hardware Store"
            body = f"Email: {email}\n\nMessage:\n{message}"
            sender_email = "thundiltraders.kollam@gmail.com"  # Replace with your email
            recipient_email = "thundiltraders.kollam@gmail.com"  # Replace with the store's email

            send_mail(subject, body, sender_email, [recipient_email])

            messages.success(request, "Your query has been sent successfully!")
        else:
            messages.error(request, "Please fill in all fields.")

    return redirect('landing_page')  # Use the correct view name

