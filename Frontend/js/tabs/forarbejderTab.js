function fillSelect(select, values, selected, labelFor) {
  if (!select) return;
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value.value;
    option.textContent = labelFor ? labelFor(value) : value.label;
    if (value.value === selected) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  select.disabled = values.length === 0;
}

function renderControls(elements, forarbejder) {
  fillSelect(
    elements.forarbejderLaw,
    (forarbejder.laws || []).map((law) => ({ value: law.eli, label: law.name })),
    forarbejder.selectedLawEli,
  );
  fillSelect(
    elements.forarbejderVersion,
    (forarbejder.versions || []).map((version) => ({
      value: version.eli,
      label: version.label,
    })),
    forarbejder.selectedVersionEli,
  );
  fillSelect(
    elements.forarbejderParagraph,
    (forarbejder.paragraphs || []).map((paragraph) => ({
      value: paragraph,
      label: `§ ${paragraph}`,
    })),
    forarbejder.selectedParagraph,
  );

  if (elements.forarbejderSteps) {
    const remaining = Math.max(1, forarbejder.remainingSteps || 1);
    elements.forarbejderSteps.max = String(remaining);
    elements.forarbejderSteps.value = String(Math.min(forarbejder.steps || remaining, remaining));
  }

  if (elements.forarbejderSearchBtn) {
    elements.forarbejderSearchBtn.disabled =
      forarbejder.running || !forarbejder.selectedParagraph || !forarbejder.selectedVersionEli;
    elements.forarbejderSearchBtn.textContent = forarbejder.running
      ? "Søger …"
      : "Find forarbejder";
  }
}

function renderNotices(elements, forarbejder) {
  if (!elements.forarbejderNotice) return;
  const messages = [];
  if (forarbejder.notice) {
    messages.push(forarbejder.notice);
  }
  if (forarbejder.skippedVersions > 0) {
    const count = forarbejder.skippedVersions;
    messages.push(
      `Du ser loven som den var i den valgte udgave. Ændringer efter den dato er ikke ` +
        `med, og ${count} nyere ${count === 1 ? "udgave springes" : "udgaver springes"} ` +
        `over, så søgningen er hurtigere.`,
    );
  }
  elements.forarbejderNotice.textContent = messages.join(" ");
  elements.forarbejderNotice.classList.toggle("hidden", messages.length === 0);
}

function renderProgress(elements, forarbejder) {
  if (!elements.forarbejderProgress) return;
  const visible = forarbejder.running || Boolean(forarbejder.progressMessage);
  elements.forarbejderProgress.classList.toggle("hidden", !visible);
  elements.forarbejderProgress.textContent = forarbejder.progressMessage || "";
}

function appendMessageList(parent, messages, className) {
  messages.forEach((message) => {
    const item = document.createElement("p");
    item.className = className;
    item.textContent = message;
    parent.appendChild(item);
  });
}

function renderSummary(parent, history) {
  const heading = document.createElement("h3");
  heading.className = "forarbejder-heading";
  heading.textContent = `${history.law_name} § ${history.paragraph_id}`;
  parent.appendChild(heading);

  const chain = document.createElement("p");
  chain.className = "forarbejder-chain";
  const steps = (history.chain || []).map((step) => step.eli).join(" → ");
  chain.textContent =
    `Kæden: ${steps}` +
    (history.reached_end
      ? "  ·  nåede enden af det maskinlæsbare materiale"
      : "  ·  standsede efter det valgte antal led — hæv det for at gå længere tilbage");
  parent.appendChild(chain);

  const changes = history.changes || [];
  if (changes.length) {
    const metrics = document.createElement("p");
    metrics.className = "forarbejder-metrics";
    metrics.textContent =
      `${changes.length} ændringer  ·  ${history.with_note} med bemærkning  ·  ` +
      `${history.confirmed} bekræftet af teksten`;
    parent.appendChild(metrics);
  }

  appendMessageList(parent, history.problems || [], "forarbejder-problem");
  appendMessageList(parent, history.notices || [], "forarbejder-notice");
}

function renderChange(parent, change, index, selectedBlocks) {
  const details = document.createElement("details");
  details.className = "forarbejder-change";

  const summary = document.createElement("summary");
  const where = (change.places || []).join(", ") || "hele paragraffen";
  summary.textContent = `${change.label} — ${where}`;
  if (!change.note_found) {
    summary.textContent += "  ·  ingen bemærkning";
  } else if (change.suspect) {
    summary.textContent += "  ·  kobling ikke bekræftet";
  }
  details.appendChild(summary);

  const consolidation = document.createElement("p");
  consolidation.className = "forarbejder-consolidation";
  consolidation.textContent = `Indarbejdet i ${change.consolidation}`;
  details.appendChild(consolidation);

  const instructionLabel = document.createElement("h4");
  instructionLabel.className = "forarbejder-subheading";
  instructionLabel.textContent = "Ændringen";
  details.appendChild(instructionLabel);

  const instruction = document.createElement("p");
  instruction.className = "forarbejder-text";
  instruction.textContent = change.text || "";
  details.appendChild(instruction);

  if (!change.note_found) {
    const problem = document.createElement("p");
    problem.className = "forarbejder-problem";
    problem.textContent = `Ingen bemærkning: ${change.note_source}`;
    details.appendChild(problem);
  } else {
    const noteLabel = document.createElement("h4");
    noteLabel.className = "forarbejder-subheading";
    noteLabel.textContent = `Specielle bemærkninger · ${change.note_source}`;
    details.appendChild(noteLabel);

    const reliability = document.createElement("p");
    if (change.confirmed) {
      reliability.className = "forarbejder-confirmed";
      reliability.textContent = `Koblingen er bekræftet: ${change.confirmation_how}.`;
    } else if (change.suspect) {
      reliability.className = "forarbejder-problem";
      reliability.textContent =
        "Koblingen kunne ikke bekræftes. Ændringen indsætter tekst, som bemærkningen " +
        "burde gengive, men den nævner hverken paragraffen eller ændringens ordlyd. " +
        "Bør efterses.";
    } else {
      reliability.className = "forarbejder-notice";
      reliability.textContent =
        "Koblingen kan ikke efterprøves: ændringen ophæver eller omnummererer uden at " +
        "indsætte tekst, så der er intet at genfinde i bemærkningen.";
    }
    details.appendChild(reliability);

    if (!change.note_precise) {
      const scope = document.createElement("p");
      scope.className = "forarbejder-notice";
      scope.textContent =
        "Bemærkningen dækker hele ændringsparagraffen — lovforslaget har intet 'Til nr.'.";
      details.appendChild(scope);
    }

    const note = document.createElement("p");
    note.className = "forarbejder-text";
    note.textContent = change.note_text || "";
    details.appendChild(note);
  }

  const actions = document.createElement("div");
  actions.className = "forarbejder-change-actions";

  const pick = document.createElement("label");
  pick.className = "forarbejder-pick";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.dataset.forarbejderPick = String(index);
  checkbox.checked = selectedBlocks.includes(index);
  pick.appendChild(checkbox);
  pick.appendChild(document.createTextNode(" Brug som fortolkningsbidrag"));
  actions.appendChild(pick);

  const documentLink = document.createElement("a");
  documentLink.className = "forarbejder-link";
  documentLink.href = change.document_url;
  documentLink.target = "_blank";
  documentLink.rel = "noopener noreferrer";
  documentLink.textContent = "Ændringsloven";
  actions.appendChild(documentLink);

  if (change.note_url) {
    const billLink = document.createElement("a");
    billLink.className = "forarbejder-link";
    billLink.href = change.note_url;
    billLink.target = "_blank";
    billLink.rel = "noopener noreferrer";
    billLink.textContent = `Lovforslag L ${change.bill_number}`;
    actions.appendChild(billLink);
  }

  if (!change.note_found && change.report_url) {
    const reportLink = document.createElement("a");
    reportLink.className = "forarbejder-link";
    reportLink.href = change.report_url;
    reportLink.target = "_blank";
    reportLink.rel = "noopener noreferrer";
    reportLink.textContent = change.report_title || "Betænkningen";
    actions.appendChild(reportLink);
  }

  details.appendChild(actions);
  parent.appendChild(details);
}

export function renderForarbejder(elements, state) {
  const forarbejder = state.forarbejder || {};
  renderControls(elements, forarbejder);
  renderNotices(elements, forarbejder);
  renderProgress(elements, forarbejder);

  const result = elements.forarbejderResult;
  if (!result) return;
  result.innerHTML = "";

  if (forarbejder.error) {
    const error = document.createElement("p");
    error.className = "forarbejder-problem";
    error.textContent = forarbejder.error;
    result.appendChild(error);
  }

  const history = forarbejder.history;
  if (!history) {
    if (!forarbejder.error) {
      const hint = document.createElement("p");
      hint.className = "forarbejder-notice";
      hint.textContent =
        "Vælg lov, udgave og paragraf, og tryk på knappen. Første opslag på nyt " +
        "materiale tager typisk 20-45 sekunder; derefter svarer diskcachen.";
      result.appendChild(hint);
    }
    if (elements.forarbejderSendPanel) {
      elements.forarbejderSendPanel.classList.add("hidden");
    }
    return;
  }

  renderSummary(result, history);

  const changes = history.changes || [];
  if (!changes.length) {
    const empty = document.createElement("p");
    empty.className = history.paragraph_exists
      ? "forarbejder-notice"
      : "forarbejder-problem";
    empty.textContent = history.paragraph_exists
      ? `§ ${history.paragraph_id} er ikke ændret i den del af kæden, vi kan nå. Det ` +
        "betyder ikke, at bestemmelsen er uden forarbejder — de ligger da før 2007, " +
        "hvor Lex Dania-XML begynder. Prøv med flere led i kæden."
      : `§ ${history.paragraph_id} blev ikke fundet i ${history.start}, og der er heller ` +
        "ingen ændringer. Svaret er tomt, fordi paragraffen ikke findes — ikke fordi " +
        "den er uændret.";
    result.appendChild(empty);
    if (elements.forarbejderSendPanel) {
      elements.forarbejderSendPanel.classList.add("hidden");
    }
    return;
  }

  const selectedBlocks = forarbejder.selectedBlocks || [];
  const list = document.createElement("div");
  list.className = "forarbejder-changes";
  changes.forEach((change, index) => renderChange(list, change, index, selectedBlocks));
  result.appendChild(list);

  if (elements.forarbejderSendPanel) {
    elements.forarbejderSendPanel.classList.remove("hidden");
  }
  if (elements.forarbejderSendBtn) {
    elements.forarbejderSendBtn.disabled = selectedBlocks.length === 0;
    elements.forarbejderSendBtn.textContent = selectedBlocks.length
      ? `Send ${selectedBlocks.length} til chatten`
      : "Send til chatten";
  }
}

export function getInitialForarbejderState() {
  return {
    laws: [],
    available: true,
    unavailableReason: "",
    selectedLawEli: "",
    versions: [],
    selectedVersionEli: "",
    remainingSteps: 1,
    skippedVersions: 0,
    notice: "",
    paragraphs: [],
    selectedParagraph: "",
    steps: 8,
    running: false,
    progressMessage: "",
    error: "",
    history: null,
    selectedBlocks: [],
  };
}
