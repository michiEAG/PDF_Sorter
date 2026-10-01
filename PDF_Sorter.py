import streamlit as st
import fitz  # PyMuPDF
import re
import os
import shutil
import zipfile
from io import BytesIO


st.set_page_config(
    page_title="PDF Splitter",
    layout="centered"
)

st.title("📄 PDF Split & Benennung")
st.write("PDFs anhand eines Textfeldes automatisch trennen und benennen")


# ============================================================
# Hilfsfunktionen
# ============================================================

def clean_filename(value):
    value = value.strip()
    return re.sub(r'[\\/:*?"<>|]', "_", value)


def extract_standort(page):
    """
    Liest den Wert rechts neben 'Standort:' aus.
    Nur für das Feld Standort.
    """

    words = page.get_text("words")

    # Standort-Feld suchen
    for word in words:

        x0, y0, x1, y1, text = word[:5]

        if text.strip().lower().rstrip(":") != "standort":
            continue

        label_right = x1
        label_center_y = (y0 + y1) / 2

        candidates = []

        # Wörter rechts vom Label auf derselben Zeile suchen
        for other_word in words:

            ox0, oy0, ox1, oy1, otext = other_word[:5]
            other_center_y = (oy0 + oy1) / 2

            if ox0 <= label_right:
                continue

            if abs(other_center_y - label_center_y) > 5:
                continue

            if otext.strip() in [":", ";"]:
                continue

            candidates.append(other_word)

        if candidates:

            candidates.sort(key=lambda item: item[0])

            return candidates[0][4].strip().rstrip(":;,")

    return None


# ============================================================
# 1) PDF Upload
# ============================================================

uploaded_file = st.file_uploader(
    "PDF hochladen",
    type=["pdf"]
)


if uploaded_file:

    # ========================================================
    # 2) Dateiname-Präfix
    # ========================================================

    default_prefix = "2026_Geräteprüfung"

    file_prefix = st.text_input(
        "Dateiname-Präfix",
        value=default_prefix
    )


    # ========================================================
    # 3) Auswahl Feld
    # ========================================================

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

        feld_name = st.text_input(
            "Feldbezeichnung (ohne Doppelpunkt)"
        )

        if feld_name:

            regex_pattern = (
                rf"{re.escape(feld_name)}\s*:\s*(.+)"
            )

        else:
            st.stop()

    else:

        feld_name = option

        feld_patterns = {
            "Inventar-Nr.": r"Inventar-Nr\.\s*:\s*(.+)",
            "Beschreibung": r"Beschreibung\s*:\s*(.+)",
            "Raum-ID": r"Raum-ID\s*:\s*(.+)"
        }

        # Für Standort wird kein Regex verwendet
        regex_pattern = feld_patterns.get(option)


    # ========================================================
    # 4) Start Button
    # ========================================================

    if st.button("🚀 PDF verarbeiten"):

        with st.spinner("PDF wird verarbeitet..."):

            # Temp-Ordner
            work_dir = "work"
            output_dir = os.path.join(
                work_dir,
                "output"
            )

            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)

            os.makedirs(output_dir)


            # PDF speichern
            pdf_path = os.path.join(
                work_dir,
                uploaded_file.name
            )

            with open(pdf_path, "wb") as f:
                f.write(uploaded_file.read())


            # PDF öffnen
            doc = fitz.open(pdf_path)

            output_docs = {}
            skipped_pages = []


            # =================================================
            # Jede Seite verarbeiten
            # =================================================

            for page_number in range(len(doc)):

                page = doc[page_number]
                text = page.get_text()

                wert = None


                # Standort speziell über die Position auslesen
                if option == "Standort":

                    wert = extract_standort(page)


                # Alle anderen Felder wie im ursprünglichen Code
                else:

                    pattern = re.compile(regex_pattern)
                    match = pattern.search(text)

                    if match:
                        wert = match.group(1).strip()


                if not wert:

                    skipped_pages.append(page_number)
                    continue


                wert = clean_filename(wert)


                if wert not in output_docs:
                    output_docs[wert] = fitz.open()


                output_docs[wert].insert_pdf(
                    doc,
                    from_page=page_number,
                    to_page=page_number
                )


            doc.close()


            # =================================================
            # Ergebnis prüfen
            # =================================================

            if not output_docs:

                st.error(
                    f"Keine Übereinstimmungen für "
                    f"'{feld_name}' gefunden."
                )

                st.write(
                    "Nicht verarbeitete Seiten:",
                    skipped_pages
                )

                st.stop()


            # =================================================
            # PDFs speichern
            # =================================================

            for wert, out_doc in output_docs.items():

                filename = f"{file_prefix}_{wert}.pdf"

                out_doc.save(
                    os.path.join(
                        output_dir,
                        filename
                    )
                )

                out_doc.close()


            # =================================================
            # ZIP erstellen
            # =================================================

            zip_buffer = BytesIO()

            with zipfile.ZipFile(
                zip_buffer,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zipf:

                for file in os.listdir(output_dir):

                    zipf.write(
                        os.path.join(output_dir, file),
                        arcname=file
                    )


            st.success(
                f"✅ Fertig! "
                f"{len(output_docs)} PDF-Datei(en) erstellt."
            )

            st.download_button(
                label="⬇️ ZIP herunterladen",
                data=zip_buffer.getvalue(),
                file_name=f"{file_prefix}_Output.zip",
                mime="application/zip"
            )
