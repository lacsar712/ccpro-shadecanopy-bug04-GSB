from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ClimateLog, Greenhouse, IrrigationCycle, Zone


class GreenhouseDeleteTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="tester", password="pass12345"
        )
        self.client.force_authenticate(user)
        self.gh = Greenhouse.objects.create(name="一号温室")

    def test_delete_blocked_when_zone_exists(self):
        Zone.objects.create(greenhouse=self.gh, zone_code="A01")
        resp = self.client.delete(f"/api/greenhouses/{self.gh.id}/")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Greenhouse.objects.filter(id=self.gh.id).count(), 1)
        self.assertIn("1 个分区", resp.data["detail"])

    def test_delete_blocked_with_zone_count_in_message(self):
        Zone.objects.create(greenhouse=self.gh, zone_code="A01")
        Zone.objects.create(greenhouse=self.gh, zone_code="A02")
        resp = self.client.delete(f"/api/greenhouses/{self.gh.id}/")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("2 个分区", resp.data["detail"])

    def test_delete_allowed_when_no_zones(self):
        resp = self.client.delete(f"/api/greenhouses/{self.gh.id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Greenhouse.objects.filter(id=self.gh.id).count(), 0)

    def test_zones_are_not_cascade_deleted(self):
        Zone.objects.create(greenhouse=self.gh, zone_code="A01")
        # 直接在数据库层删除温室（绕过 API 保护）：分区必须保留并被置空，
        # 而不是被级联删除
        self.gh.delete()
        self.assertEqual(Zone.objects.count(), 1)
        self.assertIsNone(Zone.objects.get(zone_code="A01").greenhouse_id)


class OrphanedRelationSerializationTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="tester", password="pass12345"
        )
        self.client.force_authenticate(user)
        gh = Greenhouse.objects.create(name="一号温室")
        self.zone = Zone.objects.create(greenhouse=gh, zone_code="A01")

    def test_zone_list_stable_when_greenhouse_missing(self):
        self.zone.greenhouse = None
        self.zone.save()
        resp = self.client.get("/api/zones/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(results[0]["greenhouseName"], "（未关联温室）")

    def test_climate_log_list_stable_when_greenhouse_missing(self):
        log = ClimateLog.objects.create(
            zone=self.zone,
            recorded_at=timezone.now(),
            temp_c=22.5,
            humidity_pct=55,
        )
        self.zone.greenhouse = None
        self.zone.save()
        resp = self.client.get("/api/climate-logs/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"] if "results" in resp.data else resp.data
        row = next(r for r in results if r["id"] == log.id)
        self.assertEqual(row["greenhouseName"], "（未关联温室）")
        self.assertEqual(row["zoneCode"], "A01")

    def test_irrigation_list_stable_when_greenhouse_missing(self):
        cyc = IrrigationCycle.objects.create(
            zone=self.zone,
            start_at=timezone.now(),
            duration_min=30,
            water_liters=100,
        )
        self.zone.greenhouse = None
        self.zone.save()
        resp = self.client.get("/api/irrigation-cycles/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"] if "results" in resp.data else resp.data
        row = next(r for r in results if r["id"] == cyc.id)
        self.assertEqual(row["greenhouseName"], "（未关联温室）")
