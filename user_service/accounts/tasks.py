from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .events import mark_event_published
from .models import OTPEmail, ProcessedEvent


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_otp_email(self, event):
    event_id = event["event_id"]
    event_type = event["event_type"]
    data = event["data"]

    try:
        with transaction.atomic():
            ProcessedEvent.objects.create(event_id=event_id, event_type=event_type)
    except IntegrityError:
        return "event already processed"

    tujuan = data.get("tujuan")
    otp = data["otp"]
    recipient = data["email"]

    if tujuan == "login":
        subject = "Kode OTP Login"
        title = "Verifikasi Login"
        message = "Gunakan kode OTP berikut untuk login ke akun Anda."
    elif tujuan == "reset_password":
        subject = "Reset Password OTP"
        title = "Reset Password"
        message = "Gunakan kode OTP berikut untuk mengatur ulang password Anda."
    else:
        subject = "Kode OTP"
        title = "Verifikasi"
        message = "Gunakan kode OTP berikut."

    text_content = f"{message} OTP: {otp}"
    html_content = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f4f6f8;padding:24px;">
        <div style="max-width:520px;margin:auto;background:#fff;padding:28px;border-radius:12px;">
          <h2 style="margin:0 0 8px;color:#222;">{title}</h2>
          <p style="color:#555;">{message}</p>
          <div style="font-size:28px;letter-spacing:6px;font-weight:bold;background:#1f7a4d;color:white;padding:14px 20px;border-radius:8px;display:inline-block;">
            {otp}
          </div>
          <p style="color:#777;font-size:14px;">Kode ini berlaku selama 5 menit.</p>
        </div>
      </body>
    </html>
    """

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[recipient],
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

    mark_event_published(event_id)
    return "otp email sent"


@shared_task
def cleanup_expired_otp_email():
    queryset = OTPEmail.objects.filter(kedaluwarsa_at__lt=timezone.now())
    if settings.LOAD_TESTING:
        queryset = queryset.exclude(tujuan=OTPEmail.Tujuan.LOGIN)
    deleted, _ = queryset.delete()
    return f"expired otp rows deleted: {deleted}"
