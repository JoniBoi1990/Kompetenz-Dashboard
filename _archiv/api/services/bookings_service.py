from datetime import datetime
from typing import Optional

from services.graph_client import graph_get, graph_post, graph_delete
from schemas.schemas import BookingServiceOut, BookingSlot
from config import settings

BOOKINGS_SCOPES = ["https://graph.microsoft.com/.default"]


class BookingsService:
    def __init__(self):
        self.business_id = settings.BOOKINGS_BUSINESS_ID

    async def list_services(self) -> list[BookingServiceOut]:
        data = await graph_get(f"/bookingBusinesses/{self.business_id}/services", BOOKINGS_SCOPES)
        return [
            BookingServiceOut(
                id=s["id"],
                display_name=s["displayName"],
                description=s.get("description"),
                duration_minutes=s.get("defaultDuration", 30),
            )
            for s in data.get("value", [])
        ]

    async def get_available_slots(self, service_id: str) -> list[BookingSlot]:
        # Graph staffAvailability endpoint
        data = await graph_get(
            f"/bookingBusinesses/{self.business_id}/getStaffAvailability",
            BOOKINGS_SCOPES,
        )
        slots = []
        for entry in data.get("value", []):
            for slot in entry.get("availabilityItems", []):
                if slot.get("status") == "available":
                    slots.append(BookingSlot(
                        start=slot["startDateTime"]["dateTime"],
                        end=slot["endDateTime"]["dateTime"],
                        staff_id=entry.get("staffId"),
                    ))
        return slots

    async def create_appointment(
        self,
        service_id: str,
        start: datetime,
        end: datetime,
        customer_upn: str,
        customer_name: str,
    ) -> dict:
        body = {
            "serviceId": service_id,
            "startDateTime": {"dateTime": start.isoformat(), "timeZone": "Europe/Berlin"},
            "endDateTime": {"dateTime": end.isoformat(), "timeZone": "Europe/Berlin"},
            "customers": [{"emailAddress": customer_upn, "name": customer_name}],
        }
        return await graph_post(
            f"/bookingBusinesses/{self.business_id}/appointments",
            body,
            BOOKINGS_SCOPES,
        )

    async def cancel_appointment(self, ms_booking_id: str) -> None:
        await graph_delete(
            f"/bookingBusinesses/{self.business_id}/appointments/{ms_booking_id}",
            BOOKINGS_SCOPES,
        )
