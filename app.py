import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, jsonify
from supabase import create_client

app = Flask(__name__)

# Настройки берутся из переменных окружения (задаются на Render)
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SMTP_HOST    = os.environ["SMTP_HOST"]      # например: smtp.nic.ru
SMTP_PORT    = int(os.environ["SMTP_PORT"]) # например: 465
SMTP_USER    = os.environ["SMTP_USER"]      # ваш email
SMTP_PASS    = os.environ["SMTP_PASS"]      # ваш пароль

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

EMAIL_SUBJECT = "Ваш промокод от LG Electronics"

EMAIL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Промокод от LG</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
    .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; }}
    .header {{ text-align: center; }}
    .content {{ margin-top: 20px; }}
    .footer {{ margin-top: 30px; text-align: center; font-size: 14px; color: #777; }}
    .promo-code {{ display: inline-block; padding: 10px 20px; background-color: #0073e6; color: #ffffff; font-weight: bold; border-radius: 5px; text-decoration: none; }}
    .promo-code:hover {{ background-color: #005bb5; }}
    .logo {{ width: 150px; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header"><h2>Здравствуйте!</h2></div>
    <div class="content">
      <p>Спасибо, что рассказали о своем опыте использования портативных колонок и аудиосистем — это для нас очень ценно 🎁</p>
      <p>Держите ваш промокод: <strong>{promo_code}</strong></p>
      <p>Активировать промокод можно по ссылке ниже:</p>
      <a href="https://start.ru/code" class="promo-code">Активировать промокод</a>
      <p>Промокод активен только для новых пользователей, т.е. не имевших подписку в течение минимум 120 дней к моменту его активации.</p>
    </div>
    <div class="footer">
      <p>С уважением,</p>
      <p><strong>LG Electronics</strong></p>
      <img src="https://www.lg.com/lg5-common-gp/images/common/header/logo-b2c.jpg" alt="LG logo" class="logo">
    </div>
  </div>
</body>
</html>"""


def get_next_promocode():
    """Берёт следующий свободный промокод из базы."""
    result = supabase.table("promocodes") \
        .select("code") \
        .eq("status", "free") \
        .limit(1) \
        .execute()
    if not result.data:
        return None, None
    code = result.data[0]["code"]
    return code, code


def mark_code_used(code, email):
    """Помечает промокод как использованный и сохраняет email."""
    supabase.table("promocodes") \
        .update({"status": "used", "sent_to": email}) \
        .eq("code", code) \
        .execute()


def email_already_received(email):
    """Проверяет, получал ли этот email промокод раньше."""
    result = supabase.table("promocodes") \
        .select("code") \
        .eq("sent_to", email) \
        .eq("status", "used") \
        .execute()
    return len(result.data) > 0


def send_email(to_email, promo_code):
    """Отправляет письмо с промокодом."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email

    html_body = EMAIL_HTML_TEMPLATE.format(promo_code=promo_code)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.starttls()


@app.route("/webhook", methods=["POST"])
def webhook():
    """Эндпоинт, который вызывают Яндекс.Формы при новом ответе."""
    data = request.json or request.form
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "email не передан"}), 400

    # Защита от дублей
    if email_already_received(email):
        print(f"[skip] {email} уже получал промокод")
        return jsonify({"status": "already_sent"}), 200

    # Берём промокод
    code_id, promo_code = get_next_promocode()
    if not promo_code:
        print("[error] промокоды закончились!")
        return jsonify({"error": "промокоды закончились"}), 500

    # Отправляем письмо
    send_email(email, promo_code)
    mark_code_used(code_id, email)

    print(f"[ok] {email} → {promo_code}")
    return jsonify({"status": "sent", "code": promo_code}), 200


@app.route("/health", methods=["GET"])
def health():
    """Проверка что сервис живой."""
    free = supabase.table("promocodes").select("code").eq("status", "free").execute()
    return jsonify({"status": "ok", "free_codes": len(free.data)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)