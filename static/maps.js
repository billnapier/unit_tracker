function initMap() {
  const map = new google.maps.Map(document.getElementById("map"), {
    zoom: 10,
    center: { lat: 37.333438, lng: -121.909562 },
  });

  map.data.loadGeoJson('unit_geojson')

  map.data.setStyle(function(feature) {
    return {
      title: feature.getProperty('name'),
    }});

  map.data.addListener('mouseover', function(event) {
    document.getElementById('info-box').innerHTML = 
        event.feature.getProperty('name') + '<br>' + event.feature.getProperty('address_line') + ' ' + event.feature.getProperty('city') + " " + event.feature.getProperty('state') + " " + event.feature.getProperty('zip')
  });
}

window.initMap = initMap;
