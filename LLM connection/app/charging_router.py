import heapq


# Demo coordinates: [longitude, latitude].
# These are illustrative points, not verified road geometry.
NODES = {
    "Origin": [85.818, 20.354],
    "Junction B": [85.825, 20.358],
    "Charging Station": [85.833, 20.362],
    "Junction D": [85.841, 20.367],
    "Destination": [85.850, 20.373],
}

GRAPH = {
    "Origin": {"Junction B": 2.0},
    "Junction B": {
        "Origin": 2.0,
        "Charging Station": 3.0,
    },
    "Charging Station": {
        "Junction B": 3.0,
        "Junction D": 4.0,
    },
    "Junction D": {
        "Charging Station": 4.0,
        "Destination": 3.0,
    },
    "Destination": {"Junction D": 3.0},
}


class ChargingRouter:
    def shortest_path(self, start, end):
        distances = {node: float("inf") for node in GRAPH}
        previous = {}
        distances[start] = 0
        queue = [(0, start)]

        while queue:
            distance, node = heapq.heappop(queue)

            if distance != distances[node]:
                continue

            if node == end:
                break

            for neighbor, cost in GRAPH[node].items():
                new_distance = distance + cost

                if new_distance < distances[neighbor]:
                    distances[neighbor] = new_distance
                    previous[neighbor] = node
                    heapq.heappush(
                        queue, (new_distance, neighbor)
                    )

        if distances[end] == float("inf"):
            return None, float("inf")

        path = []
        current = end

        while current != start:
            path.append(current)
            current = previous[current]

        path.append(start)
        path.reverse()

        return path, distances[end]

    def find_charging_route(self, trip):
        start = trip.get("current_location", "Origin")
        destination = trip.get("destination", "Destination")

        if start not in NODES or destination not in NODES:
            return {
                "feasible": False,
                "reason": (
                    "For this demo, current_location and destination "
                    "must match a node name in NODES."
                ),
            }

        battery = float(trip.get("battery_percent", 0))
        remaining_range = float(
            trip.get("estimated_range_km", 0)
        )

        if battery <= 0 or remaining_range <= 0:
            return {
                "feasible": False,
                "reason": "The simulated vehicle has no usable range.",
            }

        # Find the shortest route from the current location
        # to a reachable charging station, then to the destination.
        candidates = []

        for station in NODES:
            if station != "Charging Station":
                continue

            first_path, first_distance = self.shortest_path(
                start, station
            )
            second_path, second_distance = self.shortest_path(
                station, destination
            )

            if first_path is None or second_path is None:
                continue

            # Use a safety reserve: do not consume the full range.
            if first_distance > remaining_range * 0.8:
                continue

            combined_distance = first_distance + second_distance
            combined_path = first_path + second_path[1:]

            candidates.append(
                (
                    combined_distance,
                    first_distance,
                    combined_path,
                    station,
                )
            )

        if not candidates:
            return {
                "feasible": False,
                "reason": (
                    "No charging station is reachable within "
                    "the demo range constraint."
                ),
            }

        total_distance, distance_to_station, path, station = min(
            candidates, key=lambda candidate: candidate[0]
        )

        coordinates = [NODES[node] for node in path]

        return {
            "feasible": True,
            "charging_station": {
                "name": station,
                "coordinates": NODES[station],
            },
            "path": path,
            "distance_to_station_km": distance_to_station,
            "distance_km": total_distance,
            "eta_minutes": round(total_distance / 30 * 60),
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
        }