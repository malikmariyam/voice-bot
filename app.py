from flask import Flask, request, jsonify, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv
import os
import json
from datetime import datetime
from openai import OpenAI


load_dotenv()

app = Flask(__name__)


account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(account_sid, auth_token)


openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


conversations = {}


def save_conversation(call_sid, conversation):
    file_path = "conversations.json"

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}

    data[call_sid] = conversation

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Conversation for {call_sid} saved to {file_path}")


@app.get("/")
def home():
    return "Voicebot API is running"


@app.route("/initiate_call", methods=["POST"])
def initiate_call():
    data = request.get_json()
    to_number = data.get("to")

    if not to_number:
        return jsonify({"error": "Missing 'to' number"}), 400

    try:
        call = client.calls.create(
            url=f"{os.getenv('NGROK_URL')}/voice_response",
            to=to_number,
            from_=os.getenv("TWILIO_PHONE_NUMBER"),
        )
        return jsonify({"message": "Call initiated", "sid": call.sid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/incoming_call", methods=["POST"])
def incoming_call():
    print(" Incoming call received from:", request.form.get("From"))
    vr = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice_response",
        method="POST",
        timeout=5,
        bargeIn=True
    )
    gather.say("Hello! You’ve reached the AI assistant. How can I help you?", voice="alice")
    vr.append(gather)
    return Response(str(vr), mimetype="text/xml")






@app.route("/voice_response", methods=["POST"])
def voice_response():
    call_sid = request.values.get("CallSid")
    user_input = request.values.get("SpeechResult")

    if call_sid not in conversations:

        conversations[call_sid] = [
            {"role": "system", "content": "You are a helpful AI "
             "voice assistant. Always reply in short and "
             "concise sentences. Avoid long answers."}
        ]

    vr = VoiceResponse()

    if user_input:
        conversations[call_sid].append({"role": "user", "content": user_input})

        if "goodbye" in user_input.lower():
            vr.say("Goodbye! Ending the call now.", voice="alice")

            save_conversation(call_sid, conversations[call_sid])

            try:
                client.messages.create(
                    to=os.getenv("MY_VERIFIED_NUMBER"),
                    from_=os.getenv("TWILIO_PHONE_NUMBER"),
                    body=f"Call {call_sid} has ended."
                )
            except Exception as sms_err:
                print(f"SMS sending failed: {sms_err}")

            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        gpt_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conversations[call_sid]
        )

        reply_text = gpt_response.choices[0].message.content.strip()
        conversations[call_sid].append({"role": "assistant", "content": reply_text})

        gather = Gather(
            input="speech",
            action="/voice_response",
            method="POST",
            timeout=5,
            bargeIn=True
        )
        gather.say(reply_text, voice="alice")
        vr.append(gather)

    else:

        gather = Gather(
            input="speech",
            action="/voice_response",
            method="POST",
            timeout=5,
            bargeIn=True
        )
        gather.say("Hello, how can I help you today?", voice="alice")
        vr.append(gather)

    return Response(str(vr), mimetype="text/xml")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
