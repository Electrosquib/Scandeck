$(document).ready(function() {


function render_list_details() {
  $("#sites .bottom table").hide()
  $("#sites .top .num-entries").text("0 ENTRIES")
  $("#replace-sites").text("+ ADD")

  $("#talkgroups .bottom table").hide()
  $("#talkgroups .top .num-entries").text("0 ENTRIES")
  $("#replace-talkgroups").text("+ ADD")

}

$(".add-list").click(function() {
    render_list_details();
})

});
let sitesFile = null
let tgFile = null

$("#replace-sites").on("click", function() {
    $("#sites-file").click()
})

$("#replace-talkgroups").on("click", function() {
    $("#tg-file").click()
})

$("#sites-file").on("change", function(e) {
    sitesFile = e.target.files[0]
    $("#sites-name").text(sitesFile ? sitesFile.name : "No file selected")
    $("#sites .bottom table").show()
    $("#replace-sites").text("REPLACE")
    tryUpload()
})

$("#tg-file").on("change", function(e) {
    tgFile = e.target.files[0]
    $("#tg-name").text(tgFile ? tgFile.name : "No file selected")
    $("#talkgroups .bottom table").show()
    $("#replace-talkgroups").text("REPLACE")
    tryUpload()
})

function tryUpload() {
    let name = $("#list-name").val()

    if (!name || !sitesFile || !tgFile) return

    let formData = new FormData()
    formData.append("name", name)
    formData.append("sites", sitesFile)
    formData.append("talkgroups", tgFile)

    $.ajax({
        url: "/upload_scanlist",
        type: "POST",
        data: formData,
        processData: false,
        contentType: false,
        success: function(res) {
            location.reload()

        },
        error: function() {
            alert("upload failed")
        }
    })
}

function parseCSV(text) {
    return Papa.parse(text, { header: false }).data.slice(1, -1)
}

function renderSites(rows) {
    let html = ""
    for (let r of rows) {
        let site_dec = r[1]
        let site_hex = parseInt(r[2], 16)
        let nac = r[3] || ""
        let desc = r[4]
        let freqs = r.slice(9).join(",")

        html += "<tr>"
        html += `<td>${site_dec}</td>`
        html += `<td>${site_hex}</td>`
        html += `<td>${nac}</td>`
        html += `<td>${desc}</td>`
        html += `<td>${freqs}</td>`
        html += "</tr>"
    }

    $("#sites table tbody").html(html)
    $(".num-entries").first().text(rows.length + " ENTRIES")
}

function renderTG(rows) {
    let html = ""
    for (let r of rows) {
        html += "<tr>"
        for (let i = 0; i < 7; i++) {
            html += `<td>${r[i] || ""}</td>`
        }
        html += "</tr>"
    }

    $("#talkgroups table tbody").html(html)
    $("#talkgroups .num-entries").text(rows.length + " ENTRIES")
}

$("#sites-file").on("change", function(e) {
    sitesFile = e.target.files[0]
    $("#sites-name").text(sitesFile ? sitesFile.name : "")

    let reader = new FileReader()
    reader.onload = function(evt) {
        let rows = parseCSV(evt.target.result)
        renderSites(rows)
    }
    if (sitesFile) reader.readAsText(sitesFile)

    tryUpload()
})

$("#tg-file").on("change", function(e) {
    tgFile = e.target.files[0]
    $("#tg-name").text(tgFile ? tgFile.name : "")

    let reader = new FileReader()
    reader.onload = function(evt) {
        let rows = parseCSV(evt.target.result)
        renderTG(rows)
    }
    if (tgFile) reader.readAsText(tgFile)

    tryUpload()
})