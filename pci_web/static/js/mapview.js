var gMap = null;
var markers = [];

function getGPS(filename) {
  // valid: 20230818_095808.148_006619_37.4294449_127.1231462_2_1000_S_004.44_056__TuhErDw.jpg
  // invalid: G_A_V_02_0923113708856.jpg

  // if filename is invalid, return 0, 0
  if (filename.split("_").length < 5) {
    return { lat: 0, lng: 0 };
  }
  // or check -90 < lat < 90, -180 < lng < 180
  const gps = filename.split("_").slice(3, 5);
  if (
    parseFloat(gps[0]) < -90 ||
    parseFloat(gps[0]) > 90 ||
    parseFloat(gps[1]) < -180 ||
    parseFloat(gps[1]) > 180
  ) {
    return { lat: 0, lng: 0 };
  }
  return { lat: parseFloat(gps[0]), lng: parseFloat(gps[1]) };
}

function getInfoWindowContent(detail) {
    return `
        <div class="info-window">
            <div class="info-window-body">
                <table class="table table-bordered">
                    <tbody>
                        <tr>
                            <th>Condition</th>
                            <td>${detail.pav_condition}</td>
                        </tr>
                        <tr>
                            <th>PCI</th>
                            <td>${detail.pci_rating}%</td>
                        </tr>
                        <tr>
                            <th>Long&Trans length</th>
                            <td>${detail.crack_len} meter</td>
                        </tr>
                        <tr>
                            <th>Alligator area</th>
                            <td>${detail.alr_area == 0 ? 'Not found' : detail.alr_area}</td>
                        </tr>
                        <tr>
                            <th>Patching area</th>
                            <td>${detail.patching_area == 0 ? 'Not found' : detail.patching_area}</td>
                        </tr>
                        <tr>
                            <th>Pothole area</th>
                            <td>${detail.pothole_area == 0 ? 'Not found' : detail.pothole_area}</td>
                        </tr>
detailsModal
                        <tr>
                            <td colspan=2>
                                <a href="#" role="button"  data-toggle="modal" data-detail-idx="" data-target="#detailsModal">
                                    <i class="fas fa-map"></i> Show details
                                </a>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

function initMap() {
  const point = { lat: 37.260424428416364, lng: 127.55315488228202 };

  // The map, centered at the point
  gMap = new google.maps.Map(document.getElementById("mapview"), {
    zoom: 10,
    center: point,
    mapId: "90a78sf09a87f0",
  });

  const infoWindow = new google.maps.InfoWindow();

  // get details data
  const details = JSON.parse(document.getElementById("details").textContent);

  // add markers
  details.forEach((detail) => {
    const gpsCoor = getGPS(detail.img_name);
    if (gpsCoor.lat != 0 && gpsCoor.lng != 0) {
      // The marker, positioned at the point
      const marker = new google.maps.marker.AdvancedMarkerElement({
        position: gpsCoor,
        map: gMap,
        title: detail.name,
      });

      marker.addListener("click", () => {
        infoWindow.close();
        infoWindow.setContent(getInfoWindowContent(detail));
        infoWindow.open({
          anchor: marker,
          map: gMap,
          shouldFocus: false,
        });
      });

      markers.push(marker);
    }
  });
}

function clearMarkers() {
  for (let i = 0; i < markers.length; i++) {
    markers[i].setMap(null);
  }
  markers = [];
}
