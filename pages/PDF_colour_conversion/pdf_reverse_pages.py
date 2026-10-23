import os


def reverse_pdf(in_path: str, out_path: str) -> None:
    import fitz  # PyMuPDF

    src = fitz.open(in_path)
    try:
        dst = fitz.open()
        for i in range(len(src) - 1, -1, -1):
            dst.insert_pdf(src, from_page=i, to_page=i)
        dst.save(out_path)
        dst.close()
    finally:
        src.close()


def reverse_folder(input_path: str, output_path: str, include_files=None) -> str:
    os.makedirs(output_path, exist_ok=True)
    if include_files is None:
        pdfs = [os.path.join(input_path, f) for f in sorted(os.listdir(input_path)) if f.lower().endswith('.pdf')]
    else:
        pdfs = include_files

    last_out = output_path
    for src in pdfs:
        name = os.path.basename(src)
        name_noext, _ = os.path.splitext(name)
        out = os.path.join(output_path, f"{name_noext}_reversed.pdf")
        reverse_pdf(src, out)
        last_out = out
    return last_out


