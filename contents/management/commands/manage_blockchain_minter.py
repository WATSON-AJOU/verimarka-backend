from django.core.management.base import BaseCommand, CommandError

from contents.blockchain_service import ContentBlockchainService


class Command(BaseCommand):
    help = "Check or manage authorizedMinters using the blockchain owner key."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["check", "grant", "revoke"],
            help="check: 현재 민터 권한 확인, grant: 민터 권한 부여, revoke: 민터 권한 해제",
        )
        parser.add_argument(
            "--address",
            dest="address",
            default=None,
            help="대상 지갑 주소. 생략하면 WATSON_MINTER_KEY의 주소를 사용합니다.",
        )

    def handle(self, *args, **options):
        blockchain = ContentBlockchainService._create_client()

        minter_address = blockchain.get_minter_address()
        owner_address = blockchain.get_owner_address()
        target_address = options["address"] or minter_address

        if not target_address:
            raise CommandError(
                "대상 주소를 확인할 수 없습니다. --address를 주거나 WATSON_MINTER_KEY를 설정하세요."
            )

        self.stdout.write(f"owner_address={owner_address or 'unset'}")
        self.stdout.write(f"minter_address={minter_address or 'unset'}")
        self.stdout.write(f"target_address={target_address}")

        action = options["action"]
        if action == "check":
            authorized = blockchain.is_authorized_minter(target_address)
            self.stdout.write(f"authorized={str(authorized).lower()}")
            return

        if not owner_address:
            raise CommandError(
                "WATSON_OWNER_KEY가 설정되지 않아 owner 권한 작업을 수행할 수 없습니다."
            )

        desired_status = action == "grant"
        receipt = blockchain.set_minter(target_address, desired_status)
        authorized = blockchain.is_authorized_minter(target_address)

        self.stdout.write(self.style.SUCCESS(f"action={action} completed"))
        self.stdout.write(f"authorized={str(authorized).lower()}")
        self.stdout.write(f"tx_hash={receipt['tx_hash']}")
        self.stdout.write(f"block_number={receipt['block_number']}")
        self.stdout.write(f"gas_used={receipt['gas_used']}")
