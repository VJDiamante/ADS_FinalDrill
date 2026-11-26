(function () {
  var form = document.getElementById("order-form");
  if (!form) return;

  var fileInput = form.querySelector("[name=file]");
  var pagesInput = form.querySelector("[name=page_count]");
  var totalBox = document.getElementById("price-total");
  var errorBox = document.getElementById("price-error");
  var pagesHint = document.getElementById("pages-hint");
  var url = form.getAttribute("data-price-url");
  var timer = null;
  var latest = 0;

  function readValues() {
    return {
      paper_size: form.querySelector("[name=paper_size]").value,
      color_mode: form.querySelector("[name=color_mode]").value,
      page_count: pagesInput.value,
      copies: form.querySelector("[name=copies]").value
    };
  }

  function showTotal(text) {
    totalBox.textContent = text;
    errorBox.textContent = "";
  }

  function showError(text) {
    totalBox.textContent = "\u2014";
    errorBox.textContent = text;
  }

  function refreshPrice() {
    var values = readValues();
    if (!values.page_count) {
      showError("Enter the page count to see the price.");
      return;
    }
    var ticket = ++latest;
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(values)
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (result) {
        if (ticket !== latest) return;
        if (result.ok) {
          showTotal(result.body.display);
        } else {
          showError(result.body.error || "Could not calculate the price.");
        }
      })
      .catch(function () {
        if (ticket === latest) showError("Could not reach the server.");
      });
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refreshPrice, 200);
  }

  function guessPdfPages(file) {
    var reader = new FileReader();
    reader.onload = function () {
      var matches = reader.result.match(/\/Type\s*\/Page(?![s\w])/g);
      if (matches && matches.length) {
        pagesInput.value = matches.length;
        pagesHint.textContent =
          "Estimated from the PDF. The server uses its own count when it can read the file.";
        schedule();
      }
    };
    reader.readAsBinaryString(file);
  }

  fileInput.addEventListener("change", function () {
    var file = fileInput.files[0];
    pagesHint.textContent = "Word files: type the number of pages.";
    if (file && /\.pdf$/i.test(file.name) && file.size <= 10 * 1024 * 1024) {
      guessPdfPages(file);
    }
  });

  form.addEventListener("input", schedule);
  form.addEventListener("change", schedule);
  refreshPrice();
})();
