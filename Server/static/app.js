$(document).ready(function() {
    let isNew = $("body").data("is-new") === true || $("body").data("is-new") === "true";

    function parseCSV(text) {
        return Papa.parse(text, { header: false }).data.filter(function(row) {
            return row.length && row.some(function(cell) {
                return cell !== "";
            });
        }).slice(1);
    }

    function setListType(value) {
        let normalized = value === "conventional" ? "conventional" : "trunked";
        $("#list-type-value").val(normalized);
        $("#list-type").val(normalized === "conventional" ? "CONVENTIONAL" : "TRUNKED");
    }

    function ensureTableVisible(sectionSelector) {
        $(sectionSelector + " table").show();
        $(sectionSelector + " .bottom").show();
    }

    function renderSites(rows) {
        let html = "";

        for (let i = 0; i < rows.length; i++) {
            let row = rows[i];
            let siteDec = row[1] || "";
            let siteHex = row[2] || "";
            let nac = row[3] || "";
            let desc = row[4] || "";
            let freqs = row.slice(9).join(",");

            html += "<tr>";
            html += "<td>" + siteDec + "</td>";
            html += "<td>" + siteHex + "</td>";
            html += "<td>" + nac + "</td>";
            html += "<td>" + desc + "</td>";
            html += "<td>" + freqs + "</td>";
            html += "</tr>";
        }

        $("#sites table tbody").html(html);
        $("#sites .num-entries").text(rows.length + " ENTRIES");
        ensureTableVisible("#sites");
    }

    function renderTalkgroups(rows) {
        let html = "";

        for (let i = 0; i < rows.length; i++) {
            let row = rows[i];
            html += "<tr>";
            for (let col = 0; col < 7; col++) {
                html += "<td>" + (row[col] || "") + "</td>";
            }
            html += "</tr>";
        }

        $("#talkgroups table tbody").html(html);
        $("#talkgroups .num-entries").text(rows.length + " ENTRIES");
        ensureTableVisible("#talkgroups");
    }

    function previewCSV(file, renderFn) {
        if (!file) {
            return;
        }

        let reader = new FileReader();
        reader.onload = function(evt) {
            renderFn(parseCSV(evt.target.result));
        };
        reader.readAsText(file);
    }

    $("#replace-sites").on("click", function() {
        $("#sites-file").trigger("click");
    });

    $("#replace-talkgroups").on("click", function() {
        $("#tg-file").trigger("click");
    });

    $("#sites-file").on("change", function(e) {
        let file = e.target.files[0];
        $("#sites-name").text(file ? file.name : "");
        $("#replace-sites").text("REPLACE");
        previewCSV(file, renderSites);
    });

    $("#tg-file").on("change", function(e) {
        let file = e.target.files[0];
        $("#tg-name").text(file ? file.name : "");
        $("#replace-talkgroups").text("REPLACE");
        previewCSV(file, renderTalkgroups);
    });

    $("#list-type").on("click", function() {
        let nextType = $("#list-type-value").val() === "trunked" ? "conventional" : "trunked";
        setListType(nextType);
    });

    $("#uploadForm").on("submit", function(e) {
        let name = $("#list-name").val().trim();
        let sitesSelected = $("#sites-file")[0].files.length > 0;
        let tgSelected = $("#tg-file")[0].files.length > 0;

        if (!name) {
            e.preventDefault();
            alert("Please enter a scan list name.");
            return;
        }

        if (isNew && (!sitesSelected || !tgSelected)) {
            e.preventDefault();
            alert("Please choose both the sites CSV and talkgroups CSV.");
        }
    });

    setListType($("#list-type-value").val());
});
