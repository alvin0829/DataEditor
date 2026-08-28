\"\"\"CRUD checks for the API-backed XXX service spreadsheet.\"\"\"

import csv
import io

import pytest

from backend.schemas import CONTRACT_SERVICE_CSV_HEADERS


SAMPLE = {
    \"contract_no\": \"1941EM24T\",
    \"fields\": {
        \"Schedule Type\": \"Schedule B3\",
        \"Status\": \"Open\",
        \"RBQ No.\": \"RBQ-001\",
        \"Department\": \"C&ED\",
        \"Description\": \"Preventive maintenance\",
    },
}


@pytest.mark.asyncio
async def test_contract_service_create_list_update_and_delete(client):
    created_response = await client.post(\"/api/contract-services\", json=SAMPLE)
    assert created_response.status_code == 201
    created = created_response.json()
    assert created[\"contract_no\"] == \"1941EM24T\"
    assert created[\"fields\"][\"Schedule Type\"] == \"Schedule B3\"

    listed = await client.get(\"/api/contract-services\", params={\"contract_no\": \"1941EM24T\"})
    assert listed.status_code == 200
    assert listed.json()[\"total\"] == 1

    changed = await client.patch(
        f\"/api/contract-services/{created['id']}\",
        json={\"fields\": {**SAMPLE[\"fields\"], \"Status\": \"Completed\"}},
    )
    assert changed.status_code == 200
    assert changed.json()[\"fields\"][\"Status\"] == \"Completed\"

    deleted = await client.delete(f\"/api/contract-services/{created['id']}\")
    assert deleted.status_code == 204
    assert (await client.get(\"/api/contract-services\")).json()[\"total\"] == 0


@pytest.mark.asyncio
async def test_contract_service_rejects_unknown_workbook_column(client):
    response = await client.post(
        \"/api/contract-services\",
        json={\"contract_no\": \"1941EM24T\", \"fields\": {\"Not from XXX\": \"x\"}},
    )
    assert response.status_code == 422


def _csv_bytes(rows, headers=CONTRACT_SERVICE_CSV_HEADERS, prefix_rows=(), suffix_rows=()):
    content = io.StringIO(newline=\"\")
    writer = csv.writer(content)
    writer.writerows(prefix_rows)
    writer.writerow(headers)
    writer.writerows(rows)
    writer.writerows(suffix_rows)
    return content.getvalue().encode(\"utf-8\")


def _csv_row(rbq_no):
    values = [\"\"] * len(CONTRACT_SERVICE_CSV_HEADERS)
    values[0] = \"Schedule B3\"
    values[1] = \"Open\"
    values[19] = rbq_no
    return values


@pytest.mark.asyncio
async def test_rbq_number_is_unique(client):
    first = await client.post(\"/api/contract-services\", json=SAMPLE)
    assert first.status_code == 201
    second = await client.post(\"/api/contract-services\", json=SAMPLE)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_csv_import_requires_exact_headers_and_applies_contract_no(client):
    response = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={\"file\": (\"xxx.csv\", _csv_bytes([_csv_row(\"RBQ-CSV-001\")]), \"text/csv\")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body[\"imported\"] == 1
    assert body[\"items\"][0][\"contract_no\"] == \"1941EM24T\"
    assert body[\"items\"][0][\"rbq_no\"] == \"RBQ-CSV-001\"

    bad_headers = list(CONTRACT_SERVICE_CSV_HEADERS)
    bad_headers[0] = \"Wrong heading\"
    rejected = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={\"file\": (\"xxx.csv\", _csv_bytes([_csv_row(\"RBQ-CSV-002\")], bad_headers), \"text/csv\")},
    )
    assert rejected.status_code == 422
    assert (await client.get(\"/api/contract-services\")).json()[\"total\"] == 1


@pytest.mark.asyncio
async def test_csv_import_locates_heading_row_and_skips_non_service_rows(client):
    response = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={
            \"file\": (
                \"report.csv\",
                _csv_bytes(
                    [_csv_row(\"RBQ-LOCATE-001\")],
                    prefix_rows=[(\"PO, Schedule & Quotation Summary\",), (\"Generated\", \"2026-08-28\")],
                    suffix_rows=[(\"Grand total\", \"0\"), tuple([\"\"] * len(CONTRACT_SERVICE_CSV_HEADERS))],
                ),
                \"text/csv\",
            )
        },
    )
    assert response.status_code == 201
    assert response.json()[\"imported\"] == 1


@pytest.mark.asyncio
async def test_csv_import_is_atomic_when_rbq_is_duplicated(client):
    response = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={
            \"file\": (
                \"xxx.csv\",
                _csv_bytes([_csv_row(\"RBQ-DUP\"), _csv_row(\"RBQ-DUP\")]),
                \"text/csv\",
            )
        },
    )
    assert response.status_code == 409
    assert (await client.get(\"/api/contract-services\")).json()[\"total\"] == 0


# ---------------------------------------------------------------------------
# Additional targeted tests for CSV import edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_import_rejects_missing_heading_row(client):
    \"\"\"CSV that never contains the exact heading sequence is rejected.\"\"\"
    content = io.StringIO(newline=\"\")
    writer = csv.writer(content)
    writer.writerow([\"PO, Schedule & Quotation Summary\"])
    writer.writerow([\"Generated\", \"2026-08-28\"])
    writer.writerow([\"Some\", \"random\", \"data\"])
    csv_bytes = content.getvalue().encode(\"utf-8\")

    response = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={\"file\": (\"report.csv\", csv_bytes, \"text/csv\")},
    )
    assert response.status_code == 422
    detail = response.json()[\"detail\"].lower()
    assert \"heading\" in detail or \"headings\" in detail


@pytest.mark.asyncio
async def test_csv_import_rejects_malformed_service_row(client):
    \"\"\"A data row with an RBQ value but wrong column count is rejected.\"\"\"
    content = io.StringIO(newline=\"\")
    writer = csv.writer(content)
    writer.writerow(CONTRACT_SERVICE_CSV_HEADERS)
    # Valid row first
    writer.writerow(_csv_row(\"RBQ-MALFORMED-VALID\"))
    # Row with RBQ but too many columns
    bad_row = _csv_row(\"RBQ-MALFORMED-BAD\") + [\"extra\"]
    writer.writerow(bad_row)
    csv_bytes = content.getvalue().encode(\"utf-8\")

    response = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={\"file\": (\"xxx.csv\", csv_bytes, \"text/csv\")},
    )
    assert response.status_code == 422
    assert \"columns\" in response.json()[\"detail\"].lower()
    # Atomic: nothing imported
    assert (await client.get(\"/api/contract-services\")).json()[\"total\"] == 0


@pytest.mark.asyncio
async def test_csv_import_rejects_heading_only_csv_with_no_data(client):
    \"\"\"CSV that has the heading row but no service data rows is rejected.\"\"\"
    content = io.StringIO(newline=\"\")
    writer = csv.writer(content)
    writer.writerow(CONTRACT_SERVICE_CSV_HEADERS)
    # Only blank/summary rows after heading
    writer.writerow([\"Grand total\", \"0\"])
    writer.writerow([\"\"] * len(CONTRACT_SERVICE_CSV_HEADERS))
    csv_bytes = content.getvalue().encode(\"utf-8\")

    response = await client.post(
        \"/api/contract-services/import\",
        data={\"contract_no\": \"1941EM24T\"},
        files={\"file\": (\"xxx.csv\", csv_bytes, \"text/csv\")},
    )
    assert response.status_code == 422
    assert \"no data\" in response.json()[\"detail\"].lower()
