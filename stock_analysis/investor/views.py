# Create your views here.
# investor/views.py
from django.contrib.auth import login
from django.shortcuts import render, redirect
from .forms import InvestorSignupForm


def signup(request):
    if request.method == "POST":
        form = InvestorSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = InvestorSignupForm()

    return render(request, "investor/registration.html", {"form": form})
