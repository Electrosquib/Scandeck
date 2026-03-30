$(document).ready(function() {
    function renderListDetails() {
        $("#sites .bottom table").hide();
        $("#sites .top .num-entries").text("0 ENTRIES");
        $("#replace-sites").text("+ ADD");
        $("#sites-name").text("");

        $("#talkgroups .bottom table").hide();
        $("#talkgroups .top .num-entries").text("0 ENTRIES");
        $("#replace-talkgroups").text("+ ADD");
        $("#tg-name").text("");
    }

    $(".add-list").on("click", function() {
        renderListDetails();
    });
});

let sitesFile = null;
let tgFile = null;
let uploadInFlight = false;

$("#replace-sites").on("click", function() {
    $("#sites-file").click();
});

$("#replace-talkgroups").on("click", function() {
    $("#tg-file").click();
});

function parseCSV(text) {
    return Papa.parse(text, { header: false }).data.slice(1, -1);
}

function renderSites(rows) {
    let html = "";

    for (let r of rows) {
        let siteDec = r[1];
        let siteHex = parseInt(r[2], 16);
        let nac = r[3] || "";
        let desc = r[4];
        let freqs = r.slice(9).join(",");

        html += "<tr>";
        html += `<td>${siteDec}</td>`;
        html += `<td>${siteHex}</td>`;
        html += `<td>${nac}</td>`;
        html += `<td>${desc}</td>`;
        html += `<td>${freqs}</td>`;
        html += "</tr>";
    }

    $("#sites table tbody").html(html);
    $("#sites .num-entries").first().text(rows.length + " ENTRIES");
}

function renderTG(rows) {
    let html = "";

    for (let r of rows) {
        html += "<tr>";
        for (let i = 0; i < 7; i++) {
            html += `<td>${r[i] || ""}</td>`;
        }
        html += "</tr>";
    }

    $("#talkgroups table tbody").html(html);
    $("#talkgroups .num-entries").text(rows.length + " ENTRIES");
}

function syncUploadName() {
    $("#upload-name").val($("#list-name").val().trim());
}

function tryUpload() {
    let name = $("#list-name").val().trim();

    syncUploadName();

    if (!name || !sitesFile || !tgFile || uploadInFlight) {
        return;
    }

    uploadInFlight = true;
    $("#uploadForm").attr("action", "/upload_scanlist");
    $("#uploadForm").attr("method", "POST");
    $("#uploadForm").trigger("submit");
}

function previewCSV(file, renderFn) {
    if (!file) {
        return;
    }

    let reader = new FileReader();
    reader.onload = function(evt) {
        let rows = parseCSV(evt.target.result);
        renderFn(rows);
    };
    reader.readAsText(file);
}

$("#sites-file").on("change", function(e) {
    sitesFile = e.target.files[0] || null;
    $("#sites-name").text(sitesFile ? sitesFile.name : "No file selected");
    $("#sites .bottom table").show();
    $("#replace-sites").text("REPLACE");

    previewCSV(sitesFile, renderSites);
    tryUpload();
});

$("#tg-file").on("change", function(e) {
    tgFile = e.target.files[0] || null;
    $("#tg-name").text(tgFile ? tgFile.name : "No file selected");
    $("#talkgroups .bottom table").show();
    $("#replace-talkgroups").text("REPLACE");

    previewCSV(tgFile, renderTG);
    tryUpload();
});

$("#list-name").on("input change", function() {
    syncUploadName();
    tryUpload();
});
