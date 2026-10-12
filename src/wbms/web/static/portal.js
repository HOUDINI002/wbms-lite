/*
 * Captive portal behaviour. Vanilla JavaScript, no frameworks.
 *
 * Written in plain ES5 style (var, function) because the mini-browsers that
 * phones open for captive portals are often old. Package data is put on the
 * page as plain text (textContent), so nothing from the server can be run as
 * markup. Client-side checks are a convenience only: the server
 * validates the payment request again.
 */
(function () {
  "use strict";

  var PHONE_PATTERN = /^(?:\+?254|0)?([17]\d{8})$/;

  /* ---------- pure helpers (also exported for the node tests) ---------- */

  /**
   * Check a Kenyan mobile number typed by a customer.
   * Accepts 07xx, 01xx, 2547xx and +2547xx, with spaces or dashes.
   * Returns {ok: true, value: "+2547..."} or {ok: false, message: "..."}.
   */
  function normalizePhone(raw) {
    var cleaned = String(raw === null || raw === undefined ? "" : raw).replace(/[\s-]/g, "");
    if (cleaned === "") {
      return { ok: false, message: "Enter your M-Pesa phone number." };
    }
    var match = PHONE_PATTERN.exec(cleaned);
    if (!match) {
      return {
        ok: false,
        message: "Enter a Kenyan number such as 0712 345 678 or +254 712 345 678."
      };
    }
    return { ok: true, value: "+254" + match[1] };
  }

  function plural(count, one, many) {
    return count + " " + (count === 1 ? one : many);
  }

  function formatDuration(minutes) {
    var m = Number(minutes);
    if (!isFinite(m) || m <= 0) {
      return "";
    }
    if (m < 60) {
      return plural(m, "minute", "minutes");
    }
    if (m % 1440 === 0) {
      return plural(m / 1440, "day", "days");
    }
    if (m % 60 === 0) {
      return plural(m / 60, "hour", "hours");
    }
    return Math.floor(m / 60) + " h " + (m % 60) + " min";
  }

  function formatSpeed(kbps) {
    var k = Number(kbps);
    if (!isFinite(k) || k <= 0) {
      return "";
    }
    if (k >= 1000) {
      return Math.round(k / 100) / 10 + " Mbps";
    }
    return k + " kbps";
  }

  function formatData(mb) {
    if (mb === null || mb === undefined) {
      return "Unlimited data";
    }
    var n = Number(mb);
    if (!isFinite(n) || n <= 0) {
      return "";
    }
    if (n >= 1024) {
      return Math.round(n / 102.4) / 10 + " GB data";
    }
    return n + " MB data";
  }

  function formatPrice(kes) {
    var n = Number(kes);
    if (!isFinite(n)) {
      return "";
    }
    return n === 0 ? "Free" : "KES " + n;
  }

  /**
   * Turn a failed payment response into what the customer should see.
   * Returns {message: string, fields: {phone?: string, package_id?: string}}.
   */
  function describeFailure(status, body) {
    var error = body && body.error ? body.error : null;
    var raw = error && error.fields && typeof error.fields === "object" ? error.fields : {};
    var fields = {};
    if (raw.phone) {
      fields.phone = String(raw.phone);
    }
    if (raw.package_id) {
      fields.package_id = String(raw.package_id);
    }
    if (status === 400) {
      var message = raw.mac ? String(raw.mac) : "Please check the details and try again.";
      return { message: message, fields: fields };
    }
    if (status === 429) {
      return {
        message: "Too many attempts. Please wait a minute and try again.",
        fields: fields
      };
    }
    if (status === 404) {
      return {
        message: "Payments are not available right now. Please try again later.",
        fields: fields
      };
    }
    if (status >= 500) {
      return {
        message: "The payment service is not responding. Please try again in a moment.",
        fields: fields
      };
    }
    return { message: "Something went wrong. Please try again.", fields: fields };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      normalizePhone: normalizePhone,
      formatDuration: formatDuration,
      formatSpeed: formatSpeed,
      formatData: formatData,
      formatPrice: formatPrice,
      describeFailure: describeFailure
    };
  }

  if (typeof document === "undefined") {
    return;
  }

  /* ---------- page behaviour ---------- */

  function init() {
    var main = document.getElementById("main");
    var form = document.getElementById("pay-form");
    var packagesBox = document.getElementById("packages");
    var packageError = document.getElementById("package-error");
    var phoneInput = document.getElementById("phone");
    var phoneError = document.getElementById("phone-error");
    var macInput = document.getElementById("mac");
    var payButton = document.getElementById("pay-button");
    var messageBox = document.getElementById("form-message");
    if (!main || !form || !packagesBox || !phoneInput || !macInput || !payButton) {
      return;
    }

    var packagesUrl = main.getAttribute("data-packages-url");
    var paymentsUrl = main.getAttribute("data-payments-url");
    var macPresent = main.getAttribute("data-mac-present") === "true";
    var payLabel = payButton.textContent;
    var pending = false;

    payButton.disabled = !macPresent;

    function makeElement(tag, className, text) {
      var node = document.createElement(tag);
      if (className) {
        node.className = className;
      }
      if (text !== undefined) {
        node.textContent = text;
      }
      return node;
    }

    function clearChildren(node) {
      while (node.firstChild) {
        node.removeChild(node.firstChild);
      }
    }

    function showFieldError(input, errorNode, message) {
      errorNode.textContent = message;
      errorNode.hidden = false;
      if (input) {
        input.setAttribute("aria-invalid", "true");
      }
    }

    function clearFieldError(input, errorNode) {
      errorNode.textContent = "";
      errorNode.hidden = true;
      if (input) {
        input.removeAttribute("aria-invalid");
      }
    }

    function showMessage(text, kind) {
      messageBox.textContent = text;
      messageBox.className = "form-message is-" + kind;
      messageBox.hidden = false;
    }

    function clearMessage() {
      messageBox.textContent = "";
      messageBox.className = "form-message";
      messageBox.hidden = true;
    }

    function firstPackageInput() {
      return form.querySelector('input[name="package_id"]');
    }

    function selectedPackageInput() {
      return form.querySelector('input[name="package_id"]:checked');
    }

    function clearErrors() {
      clearFieldError(phoneInput, phoneError);
      clearFieldError(null, packageError);
      clearMessage();
    }

    function setPending(isPending) {
      pending = isPending;
      payButton.disabled = isPending || !macPresent;
      payButton.textContent = isPending ? "Sending request\u2026" : payLabel;
      form.setAttribute("aria-busy", isPending ? "true" : "false");
    }

    function renderPackages(packages) {
      clearChildren(packagesBox);
      packagesBox.setAttribute("aria-busy", "false");
      if (!packages.length) {
        packagesBox.appendChild(
          makeElement("p", "status", "No packages are available right now. Please check back soon.")
        );
        return;
      }
      packages.forEach(function (pkg) {
        var label = makeElement("label", "package-card");
        var input = document.createElement("input");
        input.type = "radio";
        input.name = "package_id";
        input.value = String(pkg.id);
        label.appendChild(input);
        label.appendChild(makeElement("span", "package-name", String(pkg.name)));
        label.appendChild(makeElement("span", "package-price", formatPrice(pkg.price_kes)));
        var details = [
          formatDuration(pkg.duration_minutes),
          formatSpeed(pkg.speed_kbps),
          formatData(pkg.data_limit_mb)
        ].filter(Boolean);
        label.appendChild(makeElement("span", "package-meta", details.join(" \u00b7 ")));
        packagesBox.appendChild(label);
      });
    }

    function highlightSelection() {
      var cards = packagesBox.querySelectorAll(".package-card");
      Array.prototype.forEach.call(cards, function (card) {
        var input = card.querySelector("input");
        card.className = "package-card" + (input && input.checked ? " is-selected" : "");
      });
    }

    function showLoadFailure() {
      clearChildren(packagesBox);
      packagesBox.setAttribute("aria-busy", "false");
      packagesBox.appendChild(
        makeElement("p", "status", "We could not load the packages. Check your connection.")
      );
      var retry = makeElement("button", "pay-button", "Try again");
      retry.type = "button";
      retry.addEventListener("click", loadPackages);
      packagesBox.appendChild(retry);
    }

    function loadPackages() {
      clearChildren(packagesBox);
      packagesBox.setAttribute("aria-busy", "true");
      packagesBox.appendChild(makeElement("p", "status", "Loading packages\u2026"));
      fetch(packagesUrl, { headers: { Accept: "application/json" } })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          return response.json();
        })
        .then(function (body) {
          renderPackages(body && Array.isArray(body.packages) ? body.packages : []);
        })
        .catch(showLoadFailure);
    }

    function postPayment(payload) {
      return fetch(paymentsUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload)
      }).then(function (response) {
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (body) {
            return { status: response.status, ok: response.ok, body: body };
          });
      });
    }

    packagesBox.addEventListener("change", highlightSelection);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (pending || !macPresent) {
        return;
      }
      clearErrors();

      var selected = selectedPackageInput();
      var phone = normalizePhone(phoneInput.value);
      var firstInvalid = null;

      if (!selected) {
        showFieldError(null, packageError, "Choose a package.");
        firstInvalid = firstPackageInput();
      }
      if (!phone.ok) {
        showFieldError(phoneInput, phoneError, phone.message);
        firstInvalid = firstInvalid || phoneInput;
      }
      if (firstInvalid) {
        firstInvalid.focus();
        return;
      }

      setPending(true);
      postPayment({
        package_id: Number(selected.value),
        phone: phone.value,
        mac: macInput.value
      })
        .then(function (result) {
          if (result.ok) {
            showMessage(
              "Check your phone and enter your M-Pesa PIN to finish paying. " +
                "Your access starts once the payment is confirmed.",
              "success"
            );
            return;
          }
          var failure = describeFailure(result.status, result.body);
          if (failure.fields.package_id) {
            showFieldError(null, packageError, failure.fields.package_id);
          }
          if (failure.fields.phone) {
            showFieldError(phoneInput, phoneError, failure.fields.phone);
          }
          showMessage(failure.message, "error");
        })
        .catch(function () {
          showMessage("Could not reach the server. Check your connection and try again.", "error");
        })
        .then(function () {
          setPending(false);
        });
    });

    phoneInput.addEventListener("input", function () {
      clearFieldError(phoneInput, phoneError);
    });

    loadPackages();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
