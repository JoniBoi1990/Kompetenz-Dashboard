from flask import Flask, request, jsonify, Response
from pdf_engine import create_pdf

app = Flask(__name__)


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True)
    required = {"student_name", "class_name", "datum", "zusatzinfo", "questions"}
    missing = required - data.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    pdf_bytes = create_pdf(
        questions=data["questions"],
        name=data["student_name"],
        datum=data["datum"],
        zusatzinfo=f"{data['class_name']} · {data['zusatzinfo']}",
    )
    return Response(pdf_bytes, mimetype="application/pdf")


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
