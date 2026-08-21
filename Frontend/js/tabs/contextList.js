// Kontekstlisten tegnes ens i Chat og Test. Den ligger her, så de to faner ikke
// skrider fra hinanden, når listen ændres.

const KIND_LABELS = {
  fakta: "",
  retskilde: "retskilde",
  skrivevejledning: "skrivevejledning",
};

/**
 * Tegn listen over kontekstfiler med et flueben pr. fil.
 *
 * Fluebenet afgør, om filen sendes med til modellen. Det er ikke det samme som at
 * slette den: en fil, der er slået fra, ligger stadig i sessionen og kan slås til igen.
 */
export function renderContextList(listElement, files) {
  if (!listElement) {
    return;
  }
  listElement.innerHTML = "";

  if (!files || !files.length) {
    const li = document.createElement("li");
    li.className = "context-file-item-empty";
    li.textContent = "Ingen filer uploadet endnu.";
    listElement.appendChild(li);
    return;
  }

  files.forEach((file) => {
    const isEnabled = file.enabled !== false;
    const li = document.createElement("li");
    li.className = isEnabled ? "context-file-item" : "context-file-item context-file-item-off";

    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.className = "context-file-toggle";
    toggle.checked = isEnabled;
    toggle.setAttribute("data-context-toggle-id", file.context_id);
    toggle.setAttribute(
      "aria-label",
      (isEnabled ? "Slå fra: " : "Slå til: ") + file.filename,
    );
    li.appendChild(toggle);

    const kindLabel = KIND_LABELS[file.kind] || "";
    const typeLabel = file.file_type
      ? "[" + file.file_type + (kindLabel ? " · " + kindLabel : "") + "] "
      : "";
    const noteLabel = file.extraction_note ? " - " + file.extraction_note : "";

    const name = document.createElement("span");
    name.className = "context-file-name";
    name.textContent =
      typeLabel + file.filename + " (" + (file.size_chars || 0) + " tegn)" + noteLabel;
    li.appendChild(name);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "context-file-remove";
    removeBtn.setAttribute("data-context-id", file.context_id);
    removeBtn.setAttribute("aria-label", "Fjern " + file.filename);
    removeBtn.textContent = "×";
    li.appendChild(removeBtn);

    listElement.appendChild(li);
  });
}
