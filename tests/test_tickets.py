import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from storekeeper.tickets import (
    DuplicateTicketError,
    create_ticket,
    generate_ticket_id,
    get_ticket,
    get_ticket_status,
    list_tickets,
)


class StubTicketGraph:
    def __init__(self, state_snapshot: SimpleNamespace):
        self.state_snapshot = state_snapshot
        self.received_config: dict | None = None

    def get_state(self, config: dict) -> SimpleNamespace:
        self.received_config = config
        return self.state_snapshot


class TicketRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tickets.sqlite"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_and_list_tickets_newest_first(self) -> None:
        first_ticket = create_ticket(
            "TICKET-1",
            "First ticket",
            database_path=self.database_path,
        )
        second_ticket = create_ticket(
            "TICKET-2",
            "Second ticket",
            database_path=self.database_path,
        )

        tickets = list_tickets(database_path=self.database_path)

        self.assertEqual(
            [ticket["ticket_id"] for ticket in tickets],
            ["TICKET-2", "TICKET-1"],
        )
        self.assertEqual(first_ticket["ticket_text"], "First ticket")
        self.assertEqual(second_ticket["ticket_text"], "Second ticket")

    def test_duplicate_ticket_id_raises_specific_error(self) -> None:
        create_ticket(
            "TICKET-1",
            "Original ticket",
            database_path=self.database_path,
        )

        with self.assertRaisesRegex(DuplicateTicketError, "already been used"):
            create_ticket(
                "TICKET-1",
                "Different ticket",
                database_path=self.database_path,
            )

    def test_get_ticket_returns_one_record_or_none(self) -> None:
        create_ticket(
            "TICKET-1",
            "Original ticket",
            database_path=self.database_path,
        )

        ticket = get_ticket("TICKET-1", database_path=self.database_path)
        missing_ticket = get_ticket("UNKNOWN", database_path=self.database_path)

        assert ticket is not None
        self.assertEqual(ticket["ticket_text"], "Original ticket")
        self.assertIsNone(missing_ticket)

    def test_generated_ticket_ids_are_unique(self) -> None:
        generated_ticket_ids = {generate_ticket_id() for _ in range(100)}

        self.assertEqual(len(generated_ticket_ids), 100)
        self.assertTrue(
            all(ticket_id.startswith("TICKET-") for ticket_id in generated_ticket_ids)
        )


class TicketStatusTests(unittest.TestCase):
    def test_status_is_not_found_when_no_checkpoint_values_exist(self) -> None:
        ticket_graph = StubTicketGraph(
            SimpleNamespace(values={}, interrupts=())
        )

        status = get_ticket_status("TICKET-1", ticket_graph)

        self.assertEqual(status, "not_found")
        self.assertEqual(
            ticket_graph.received_config,
            {"configurable": {"thread_id": "TICKET-1"}},
        )

    def test_status_is_pending_when_checkpoint_is_interrupted(self) -> None:
        ticket_graph = StubTicketGraph(
            SimpleNamespace(
                values={"ticket_text": "Cancel order #1001."},
                interrupts=(object(),),
            )
        )

        status = get_ticket_status("TICKET-2", ticket_graph)

        self.assertEqual(status, "pending_approval")

    def test_status_is_resolved_when_checkpoint_has_no_interrupt(self) -> None:
        ticket_graph = StubTicketGraph(
            SimpleNamespace(
                values={"ticket_outcome": "resolved"},
                interrupts=(),
            )
        )

        status = get_ticket_status("TICKET-3", ticket_graph)

        self.assertEqual(status, "resolved")


if __name__ == "__main__":
    unittest.main()
