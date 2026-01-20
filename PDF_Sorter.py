import streamlit as st
import fitz  # PyMuPDF
import re
import os
import shutil
import zipfile
from io import BytesIO

st.set_page_config(page_title="PDF Splitter", layout="centered")

st.title("📄 PDF Split & Benennung")
st.write("PDFs anhand eines Textfeldes automatisch trennen und benennen")

# =========================
# 1) PDF Upload
# =========================
uploaded_file = st.file_uploader("PDF hochladen", type=["pdf"])

if uploaded_file:

    # =========================
    # 2) Dateiname-Präfix
    # =========================
    default_prefix = "2026_Geräteprüfung"
    file_prefix = st.text_input(
        "Dateiname-Präfix",
        value=default_prefix
    )

    # =========================
    # 3) Auswahl Feld
    # =========================
    option = st.selectbox(
        "Nach welchem Feld soll aufgeteilt werden?",
        [
            "Inventar-Nr.",
            "Beschreibung",
            "Raum-ID",
            "Standort",
            "Benutzerdefiniert"
        ]
    )

    if option == "Benutzerdefiniert":
        feld_name = st.text_input("Feldbezeichnung (ohne Doppelpunkt)")
        if feld_name:
            regex_pattern = rf"{re.escape(feld_name)}\s*:\s*(.+)"
        else:
            st.stop()
    else:
        feld_name = option
        feld_patterns = {
            "Inventar-Nr.": r"Inventar-Nr\.\s*:\s*(.+)",
            "Beschreibung": r"Beschreibung\s*:\s*(.+)",
            "Raum-ID": r"Raum-ID\s*:\s*(.+)",
            "Standort": r"Standort\s*:\s*(.+)"
        }
        regex_pattern = feld_patterns[option]

    # =========================
    # 4) Start Button
    # =========================
    if st.button("🚀 PDF verarbeiten"):

        with st.spinner("PDF wird verarbeitet..."):

            # Temp-Ordner
            work_dir = "work"
            output_dir = os.path.join(work_dir, "output")

            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)
            os.makedirs(output_dir)

            # PDF speichern
            pdf_path = os.path.join(work_dir, uploaded_file.name)
            with open(pdf_path, "wb") as f:
                f.write(uploaded_file.read())

            # PDF öffnen
            doc = fitz.open(pdf_path)
            pattern = re.compile(regex_pattern)
            output_docs = {}

            for page_number in range(len(doc)):
                text = doc[page_number].get_text()
                match = pattern.search(text)
                if not match:
                    continue

                wert = match.group(1).strip()
                wert = re.sub(r'[\\/:*?"<>|]', '_', wert)

                if wert not in output_docs:
                    output_docs[wert] = fitz.open()

                output_docs[wert].insert_pdf(
                    doc,
                    from_page=page_number,
                    to_page=page_number
                )

            doc.close()

            if not output_docs:
                st.error(f"Keine Übereinstimmungen für '{feld_name}' gefunden.")
                st.stop()

            # PDFs speichern
            for wert, out_doc in output_docs.items():
                filename = f"{file_prefix}_{wert}.pdf"
                out_doc.save(os.path.join(output_dir, filename))
                out_doc.close()

            # ZIP im Speicher erzeugen
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file in os.listdir(output_dir):
                    zipf.write(
                        os.path.join(output_dir, file),
                        arcname=file
                    )

            st.success("✅ Fertig! ZIP kann heruntergeladen werden.")

            st.download_button(
                label="⬇️ ZIP herunterladen",
                data=zip_buffer.getvalue(),
                file_name=f"{file_prefix}_Output.zip",
                mime="application/zip"
            )
