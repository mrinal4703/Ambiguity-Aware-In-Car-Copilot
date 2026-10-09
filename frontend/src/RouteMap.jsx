import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

function FitRoute({ positions }) {
  const map = useMap();

  useEffect(() => {
    if (positions.length > 0) {
      map.fitBounds(positions, { padding: [35, 35] });
    }
  }, [map, positions]);

  return null;
}

const stationIcon = L.divIcon({
  className: "",
  html: '<div style="background:#16a34a;color:white;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:18px;border:2px solid white">⚡</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
});

export default function RouteMap({ route }) {
  const coordinates = route?.geometry?.coordinates;

  if (!coordinates || coordinates.length === 0) {
    return null;
  }

  // GeoJSON coordinates are [longitude, latitude].
  // Leaflet positions are [latitude, longitude].
  const positions = coordinates.map(([lon, lat]) => [lat, lon]);

  const stationCoordinates =
    route.charging_station?.coordinates;

  const stationPosition = stationCoordinates
    ? [stationCoordinates[1], stationCoordinates[0]]
    : null;

  return (
    <div style={{ height: "420px", width: "100%", marginTop: "20px" }}>
      <MapContainer
        center={positions[0]}
        zoom={13}
        style={{ height: "100%", width: "100%", borderRadius: "12px" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <FitRoute positions={positions} />

        <Polyline
          positions={positions}
          pathOptions={{ color: "#2563eb", weight: 5 }}
        />

        <Marker position={positions[0]}>
          <Popup>Current location / start</Popup>
        </Marker>

        {stationPosition && (
          <Marker position={stationPosition} icon={stationIcon}>
            <Popup>
              Charging Station
              <br />
              Demo charging stop
            </Popup>
          </Marker>
        )}

        <Marker position={positions[positions.length - 1]}>
          <Popup>Destination</Popup>
        </Marker>
      </MapContainer>
    </div>
  );
}