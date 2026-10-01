import streamlit as st
import fitz
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


def clean_filename(value):
    value = value.strip()
    value = re.sub(r'[\\/:*?"<>|]', "_", value)
    value = re.sub(r"\s+", "_", value)
    return value.strip("_")


def normalize_text(value):
    return value.strip().lower().rstrip(":;,")


def extract_value_by_position(page, field_name):
    """
    Liest den Wert rechts neben einem Feldnamen anhand
    der Position auf der PDF-Seite aus.
    """

    words = page.get_text("words")

    if not words:
        return None

    field_parts = field_name.strip().split()
    field_parts = [normalize_text(part) for part in field_parts]

    label_start = None
    label_end = None

    # Feldbezeichnung suchen
    for index in range(len(words)):

        current_text = normalize_text(words[index][4])

        # Einfaches Feld, z. B. Standort oder Prüfdatum
        if len(field_parts) == 1:

            if current_text == field_parts[0]:
                label_start = words[index]
                label_end = words[index]
                break

        # Mehrteiliges Feld, z. B. Nächste Prüfung
        else:

            if index + len(field_parts) > len(words):
                continue

            found = True

            for part_index, field_part in enumerate(field_parts):

                current_word = words[index + part_index]
                current_word_text = normalize_text(current_word[4])

                if current_word_text != field_part:
                    found = False
                    break

            if found:
                label_start = words[index]
                label_end = words[index + len(field_parts) - 1]
                break

    if label_start is None:
        return None

    label_right = label_end[2]
    label_center_y = (label_start[1] + label_end[3]) / 2

    # Bekannte Feldnamen nicht versehentlich als Wert verwenden
    known_fields = [
        "Inventar-Nr.",
        "Serien-Nr.",
        "Standort",
        "Beschreibung",
        "Hersteller",
        "Schutzklasse",
        "Sich./Leistung",
        "Raum-ID",
        "Prüfintervall",
        "Prüfungsgruppe",
        "Prüfmittel",
        "Prüfer",
        "Prüfergebnis",
        "Prüfdatum",
        "Nächste Prüfung"
    ]

    known_fields_normalized = [
        normalize_text(field)
        for field in known_fields
    ]

    candidates = []

    # Wörter rechts neben dem Feld auf derselben Zeile suchen
    for word in words:

        x0, y0, x1, y1, text = word[:5]
        word_center_y = (y0 + y1) / 2
        normalized_word = normalize_text(text)

        if x0 <= label_right:
            continue

        if abs(word_center_y - label_center_y) > 8:
            continue

        if normalized_word in ["", ":", ";", ","]:
            continue

        # Nächstes Feld nicht als Wert verwenden
        if normalized_word in known_fields_normalized:
            continue

        candidates.append(word)

    if not candidates:
        return None

    candidates.sort(key=lambda word: word[0])

    return candidates[0][4].strip().rstrip(":;,")


uploaded_file = st.file_uploader(
    "PDF hochladen",
    type=["pdf"]
)


if uploaded_file:

    default_prefix = "2026_Geräteprüfung"

    file_prefix = st.text_input(
        "Dateiname-Präfix",
        value=default_prefix
    )

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

        if not feld_name:
            st.stop()

        regex_pattern = None

    else:

        feld_name = option

        feld_patterns = {
            "Inventar-Nr.": r"Inventar-Nr\.\s*:\s*(.+)",
            "Beschreibung": r"Beschreibung\s*:\s*(.+)",
            "Raum-ID": r"Raum-ID\s*:\s*(.+)"
        }

        regex_pattern = feld_patterns.get(option)


    if st.button("🚀 PDF verarbeiten"):

        with st.spinner("PDF wird verarbeitet..."):

            work_dir = "work"
            output_dir = os.path.join(work_dir, "output")

            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)

            os.makedirs(output_dir)

            pdf_path = os.path.join(
                work_dir,
                uploaded_file.name
            )

            with open(pdf_path, "wb") as file:
                file.write(uploaded_file.read())

            doc = fitz.open(pdf_path)

            output_docs = {}
            skipped_pages = []

            for page_number in range(len(doc)):

                page = doc[page_number]
                text = page.get_text()
                wert = None

                # Standort und benutzerdefinierte Felder
                # über die Position auslesen
                if option == "Standort" or option == "Benutzerdefiniert":

                    wert = extract_value_by_position(
                        page,
                        feld_name
                    )

                # Die ursprünglichen Standardfelder
                # weiterhin über Regex auslesen
                else:

                    pattern = re.compile(regex_pattern)
                    match = pattern.search(text)

                    if match:
                        wert = match.group(1).strip()

                if not wert:
                    skipped_pages.append(page_number)
                    continue

                wert = clean_filename(wert)

                if not wert:
                    skipped_pages.append(page_number)
                    continue

                if wert not in output_docs:
                    output_docs[wert] = fitz.open()

                output_docs[wert].insert_pdf(
                    doc,
                    from_page=page_number,
                    to_page=page_number
                )

            doc.close()

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

            created_files = []

            for wert, out_doc in output_docs.items():

                filename = f"{file_prefix}_{wert}.pdf"
                output_path = os.path.join(
                    output_dir,
                    filename
                )

                out_doc.save(output_path)
                out_doc.close()

                created_files.append(filename)

            zip_buffer = BytesIO()

            with zipfile.ZipFile(
                zip_buffer,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zipf:

                for filename in created_files:

                    file_path = os.path.join(
                        output_dir,
                        filename
                    )

                    zipf.write(
                        file_path,
                        arcname=filename
                    )

            st.success(
                f"✅ Fertig! "
                f"{len(created_files)} PDF-Datei(en) erstellt."
            )

            st.download_button(
                label="⬇️ ZIP herunterladen",
                data=zip_buffer.getvalue(),
                file_name=f"{file_prefix}_Output.zip",
                mime="application/zip"
            )
