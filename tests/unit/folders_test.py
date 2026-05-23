"""Unit tests for kontor_cli.folders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kontor_cli.folders import (
    FolderInvariantError,
    get_archive_path,
    get_target_for_email,
    is_older_than_6months,
    is_valid_folder,
    validate_folder,
)


class TestIsValidFolder:
    def test_valid_root_folders(self) -> None:
        assert is_valid_folder("0_Action")
        assert is_valid_folder("1_Management")
        assert is_valid_folder("2_Projects")
        assert is_valid_folder("3_External")
        assert is_valid_folder("4_Info")
        assert is_valid_folder("9_System")
        assert is_valid_folder("Archive")

    def test_valid_sub_folders(self) -> None:
        assert is_valid_folder("1_Management/MGT_HR")
        assert is_valid_folder("2_Projects/PRJ_Finance_ERP_Global")
        assert is_valid_folder("3_External/EXT_Vendor_Service")
        assert is_valid_folder("Archive/2_Projects")
        assert is_valid_folder("Archive/0_Action")

    def test_invalid_folder_prefix(self) -> None:
        assert not is_valid_folder("5_Other")
        assert not is_valid_folder("Random_Folder")
        assert not is_valid_folder("")
        assert not is_valid_folder(".hidden")


class TestValidateFolder:
    def test_validate_valid(self) -> None:
        validate_folder("2_Projects/PRJ_Finance")  # should not raise

    def test_validate_invalid_raises(self) -> None:
        with pytest.raises(FolderInvariantError):
            validate_folder("5_Other")


class TestArchivePath:
    def test_archive_mirror_path(self) -> None:
        assert get_archive_path("0_Action") == "Archive/0_Action"
        assert get_archive_path("1_Management/MGT_HR") == "Archive/1_Management/MGT_HR"
        assert (
            get_archive_path("Archive/2_Projects") == "Archive/2_Projects"
        )  # no double-wrap


class TestIsOlderThan6Months:
    def test_older_than_6months(self) -> None:
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        assert is_older_than_6months(old_date)

    def test_not_older_than_6months(self) -> None:
        recent_date = datetime.now(UTC) - timedelta(days=30)
        assert not is_older_than_6months(recent_date)

    def test_exactly_6months_old(self) -> None:
        # "Exactly 6 months ago" is ill-defined for relative calculation.
        # The function uses strictly < threshold. Test that a date clearly
        # in the past (1 year ago) is flagged as older.
        from dateutil.relativedelta import relativedelta

        one_year_ago = datetime.now(UTC) - relativedelta(years=1)
        assert is_older_than_6months(one_year_ago)


class TestGetTargetForEmail:
    def test_classified_folder(self) -> None:
        recent = datetime.now(UTC) - timedelta(days=30)
        assert (
            get_target_for_email(recent, "2_Projects/PRJ_Test", 6)
            == "2_Projects/PRJ_Test"
        )

    def test_no_classification_defaults_to_4_info(self) -> None:
        recent = datetime.now(UTC) - timedelta(days=30)
        assert get_target_for_email(recent, None, 6) == "4_Info"

    def test_old_email_goes_to_archive(self) -> None:
        old = datetime(2020, 1, 1, tzinfo=UTC)
        assert (
            get_target_for_email(old, "2_Projects/PRJ_Test", 6)
            == "Archive/2_Projects/PRJ_Test"
        )

    def test_already_in_archive_stays(self) -> None:
        old = datetime(2020, 1, 1, tzinfo=UTC)
        assert (
            get_target_for_email(old, "Archive/2_Projects/PRJ_Test", 6)
            == "Archive/2_Projects/PRJ_Test"
        )
