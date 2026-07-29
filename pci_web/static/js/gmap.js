/** Google Map Functions **/

function initMap() {
    let gmap = new google.maps.Map(document.getElementById('map'), {  // document.getElementById('map')
        center: {lat: 37.397, lng: 127.644},
        zoom: 9,
        streetViewControl: false
    });

    let infowindow = new google.maps.InfoWindow;

    let basePath = './../static/images/';

    let icons = {
        red: {
            icon: basePath + "red_marker.png"
        },
        green: {
            icon: basePath + "green_marker.png"
        },
        blue: {
            icon: basePath + "blue_marker.png"
        },
        orange: {
            icon: basePath + "orange_marker.png"
        }
    };

    let features = [
        /*{
            position: new google.maps.LatLng(37.797, 127.244),
            type: 'green',
            url: "/model"
        },*/
        {
            position: new google.maps.LatLng(37.19701,127.544799),
            type: 'blue',
            title: 'Icheon-slope',
            url: "/model"
        },
        {
            position: new google.maps.LatLng(37.597, 127.944),
            type: 'red',
            title: 'Slope1',
            url: './../../pages/model_loader.html'
        },
        {
            position: new google.maps.LatLng(37.228278,127.893258),
            type: 'blue',
            title: 'Wonju slope',
            url: "/model"
        }
    ];

    features.forEach(function (feature) {
        let marker = new google.maps.Marker({
            map: gmap,
            animation: google.maps.Animation.DROP,
            position: feature.position,
            icon: icons[feature.type].icon
        });

        marker.addListener('click', function () {
            infowindow.setContent(makeContent(feature.title, feature.url));
            infowindow.open(gmap, marker);
        }, false);
    });
}

function makeContent(title, page_url) {
    return '<div id="content">' +
        '<div id="siteNotice">Slope Information</div>' +
        '<h3 id="firstHeading" class="firstHeading" style="padding: 2px;">'+title+'</h3>' +
        '<div id="bodyContent">' +
        '<table class="table table-sm table-striped table-bordered ">' +
        '<tbody>' +
        '<tr><th><b>Location</b></th><td> 32.5423, 126.3432</td></tr>'+
        '<tr><th><b>Adress</b></th><td> Icheon, High-way 154-24 </td></tr>'+
        '<tr><th><b>Status</b></th><td> Normal (checking required)</td></tr>'+
        '<tr><th><b>Last</b></th><td> Oct. 24, 2019 </td></tr>'+
        '<tr><th><b>Slope angle</b></th><td> 35&#176; </td></tr>'+
        '<tr><th><b>Slope height</b></th><td> 50m </td></tr>'+
        '</tbody>'+
        '</table>'+
        '<hr><p><h5>Images:</h5>' +
        '<img src="/uploads/slope1/img/image_20191105_010045_810895.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<img src="/uploads/slope1/img/image_20191105_010047_842072.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<img src="/uploads/slope1/img/image_20191105_010049_870566.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<img src="/uploads/slope1/img/image_20191105_010051_899754.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<br>'+
        '<img src="/uploads/slope1/img/image_20191105_010053_933160.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<img src="/uploads/slope1/img/image_20191105_010055_961810.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<img src="/uploads/slope1/img/image_20191105_010057_994631.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '<img src="/uploads/slope1/img/image_20191105_010102_060676.JPG" alt="" style="max-width: 100px; margin: 2px;">'+
        '</p>' +
        '<p style="text-align: right;">' +
        '<a href="#" class="btn btn-sm btn-info">Images</a> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' +
        '<a class="btn btn-info btn-sm" href="' + page_url + '" target="_blank">3D models</a><p>' +
        '</div>' +
        '</div>';
}
/**
 * Project Folder Create Map
 * */

let marker = null;
function initPosition() {
    let gmap = new google.maps.Map(document.getElementById('map'), {
        center: {lat: 37.397, lng: 127.644},
        zoom: 8,
        streetViewControl: false,
        fullscreen: false,
        draggableCursor: 'crosshair'
    });

    google.maps.event.addListener(gmap, 'click', function (event) {
        addMarker(event.latLng, gmap);

        window.document.getElementById('id_lat').value = event.latLng.lat();
        window.document.getElementById('id_lng').value = event.latLng.lng();
    });
}

function addMarker(location, map) {
    if(marker !== null ){
        marker.setMap(null);
    }
    marker = new google.maps.Marker({
        position: location,
        map: map,
    });
}