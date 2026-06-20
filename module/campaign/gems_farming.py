from module.base.button import Button
from module.base.timer import Timer
from module.base.utils import load_image
from module.campaign.campaign_base import CampaignBase
from module.campaign.run import CampaignRun
from module.combat.assets import BATTLE_PREPARATION
from module.equipment.assets import *
from module.equipment.fleet_equipment import FleetEquipment
from module.exception import CampaignEnd, GameStuckError, GameTooManyClickError, ScriptError
from module.handler.assets import AUTO_SEARCH_MAP_OPTION_OFF
from module.logger import logger
from module.map.assets import FLEET_PREPARATION, MAP_PREPARATION
from module.retire.assets import (
    DOCK_CHECK,
    TEMPLATE_BOGUE, TEMPLATE_HERMES, TEMPLATE_LANGLEY, TEMPLATE_RANGER,
    TEMPLATE_CASSIN_1, TEMPLATE_CASSIN_2, TEMPLATE_DOWNES_1, TEMPLATE_DOWNES_2,
    TEMPLATE_AULICK, TEMPLATE_FOOTE
)

from module.retire.dock import Dock
from module.retire.scanner import ShipScanner
from module.ui.assets import BACK_ARROW
from module.ui.page import page_fleet

SIM_VALUE = 0.90

# Equipment preset UI, hand-measured on CN 1280x720 (panel layout is server-independent).
EQUIP_PRESET_ENTER = Button(
    area=(1140, 88, 1231, 111), color=(213, 150, 70),
    button=(1140, 88, 1231, 111), name='EQUIP_PRESET_ENTER')
EQUIP_PRESET_RECORD_1 = Button(
    area=(1208, 258, 1245, 328), color=(112, 146, 182),
    button=(1208, 258, 1245, 328), name='EQUIP_PRESET_RECORD_1')
# Fixed repair-tool template cropped from the equipment storage (same rendering as the
# equipment-selection list), so list-to-list template matching is reliable (~0.95).
REPAIR_TOOL_FILE = './assets/cn/equipment/EQUIP_REPAIR_TOOL.png'


class GemsCampaignOverride(CampaignBase):

    def handle_combat_low_emotion(self):
        """
        Overwrite info_handler.handle_combat_low_emotion()
        If change vanguard is enabled, withdraw combat and change flagship and vanguard
        """
        if self.config.GemsFarming_ChangeVanguard == 'disabled':
            result = self.handle_popup_confirm('IGNORE_LOW_EMOTION')
            if result:
                # Avoid clicking AUTO_SEARCH_MAP_OPTION_OFF
                self.interval_reset(AUTO_SEARCH_MAP_OPTION_OFF)
            return result

        if self.handle_popup_cancel('IGNORE_LOW_EMOTION'):
            self.config.GEMS_EMOTION_TRIGGERED = True
            logger.hr('EMOTION WITHDRAW')

            while 1:
                self.device.screenshot()

                if self.handle_story_skip():
                    continue
                if self.handle_popup_cancel('IGNORE_LOW_EMOTION'):
                    continue

                if self.appear(BATTLE_PREPARATION, offset=(20, 20), interval=2):
                    self.device.click(BACK_ARROW)
                    continue
                if self.handle_auto_search_exit():
                    continue
                if self.is_in_stage():
                    break

                if self.is_in_map():
                    self.withdraw()
                    break

                if self.appear(FLEET_PREPARATION, offset=(20, 50), interval=2) \
                        or self.appear(MAP_PREPARATION, offset=(20, 20), interval=2):
                    self.enter_map_cancel()
                    break
            raise CampaignEnd('Emotion withdraw')


class GemsFarming(CampaignRun, FleetEquipment, Dock):
    # Set to False to disable equipment transfer entirely (only swap ships, no equipment record/take-on).
    # The equipment-upgrade page assets are unmaintained and may break again on game updates.
    CHANGE_EQUIP = True

    def load_campaign(self, name, folder='campaign_main'):
        super().load_campaign(name, folder)

        class GemsCampaign(GemsCampaignOverride, self.module.Campaign):
            pass

        self.campaign = GemsCampaign(device=self.campaign.device, config=self.campaign.config)
        self.campaign.config.override(Emotion_Mode='ignore')
        self.campaign.config.override(EnemyPriority_EnemyScaleBalanceWeight='S1_enemy_first')

    @property
    def change_vanguard(self):
        return 'ship' in self.config.GemsFarming_ChangeVanguard

    @property
    def fleet_to_attack(self):
        if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
            return self.config.Fleet_Fleet2
        else:
            return self.config.Fleet_Fleet1

    def _unload_equipment(self, enter):
        """
        Take all equipment off the current ship BEFORE swapping it out, so those
        items become free and the replacement ship can equip them. This is the
        original flow's "unload old ship" step (do not remove it).

        Non-fatal: on stuck, skip and recover to page_fleet.
        """
        try:
            self.fleet_enter_ship(enter)
            self.ship_equipment_take_off()
            self.fleet_back()
        except (GameStuckError, GameTooManyClickError) as e:
            logger.warning(f'Unload old equipment failed, skip ({e})')
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            self.ui_ensure(page_fleet)

    def _equip_repair_tools(self, enter):
        """
        Flagship: unload everything, then equip a repair tool in the two auxiliary
        slots (3, 4) by matching a fixed repair-tool template against the
        equipment-selection list.

        Non-fatal: on stuck, skip and recover to page_fleet so the gems run
        continues with a plain ship swap instead of crashing the whole task.
        """
        try:
            self.fleet_enter_ship(enter)
            self.ship_equipment_take_off()
            # Reuse the existing image take-on matcher, but with a fixed repair-tool
            # template injected for the two auxiliary slots instead of a recording.
            repair = load_image(REPAIR_TOOL_FILE)
            self.equipment_list = {3: repair, 4: repair}
            self.ship_equipment_take_on_image(index_list=[3, 4])
            self.fleet_back()
        except (GameStuckError, GameTooManyClickError) as e:
            logger.warning(f'Equip flagship repair tools failed, skip ({e})')
            self.equipment_list = {}
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            self.ui_ensure(page_fleet)

    def _equip_preset(self, enter):
        """
        Vanguard: open the equipment preset tab, unload everything, then apply
        preset record 1 (the loadout the user saved for the vanguard).

        Non-fatal: see _equip_repair_tools.
        """
        try:
            self.fleet_enter_ship(enter)
            # Switch to the preset tab (记录 rows / 更换 buttons become visible).
            # These preset buttons have NO template file, so they cannot be used as a
            # template check_button (ui_click -> appear -> load_image(None) crashes).
            # Verify the panel opened by color instead (appear with offset=False).
            self._open_preset_tab()
            # Unload all equipment (卸载所有装备 == EQUIP_OFF, already handled).
            self.ship_equipment_take_off()
            # Apply preset record 1 (第一行的 更换).
            self._apply_preset_record_1()
            self.fleet_back()
        except (GameStuckError, GameTooManyClickError) as e:
            logger.warning(f'Equip vanguard preset failed, skip ({e})')
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            self.ui_ensure(page_fleet)

    def _open_preset_tab(self, skip_first_screenshot=True):
        """
        Click the in-game equipment 预设 (preset) tab until a record row appears.
        Verified by color (the preset buttons have no template file, so appear() is
        called with offset=False to use color matching instead of template matching).
        """
        logger.info('Open equipment preset tab')
        click_timer = Timer(3)
        confirm_timer = Timer(10).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # End: a preset record row (更换 button) is visible.
            if self.appear(EQUIP_PRESET_RECORD_1, offset=False):
                break
            if confirm_timer.reached():
                logger.warning('Open preset tab timeout')
                break
            if click_timer.reached():
                self.device.click(EQUIP_PRESET_ENTER)
                click_timer.reset()

    def _apply_preset_record_1(self, skip_first_screenshot=True):
        """
        Click 记录1 的 更换 (apply preset) and confirm, until the equip info bar shows.
        """
        logger.info('Apply equipment preset record 1')
        click_timer = Timer(3)
        confirm_timer = Timer(10, count=20).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if self.handle_popup_confirm('EQUIP_PRESET'):
                continue
            # End: equip succeeded (info bar shows after applying the preset).
            if self.info_bar_count():
                break
            # Safety timeout: don't loop forever if the preset is empty / UI differs.
            if confirm_timer.reached():
                logger.warning('Apply preset record 1 timeout')
                break
            if click_timer.reached():
                self.device.click(EQUIP_PRESET_RECORD_1)
                click_timer.reset()

    def flagship_change(self):
        """
        Change flagship, then equip repair tools in its two auxiliary slots.

        Returns:
            bool: True if flagship changed.
        """
        logger.hr('Change flagship', level=1)
        self.fleet_enter(self.fleet_to_attack)

        if self.CHANGE_EQUIP:
            logger.hr('Unload flagship equipment', level=2)
            self._unload_equipment(FLEET_DETAIL_ENTER_FLAGSHIP)

        logger.hr('Change flagship', level=2)
        success = self.flagship_change_execute()

        if self.CHANGE_EQUIP:
            logger.hr('Equip flagship repair tools', level=2)
            self._equip_repair_tools(FLEET_DETAIL_ENTER_FLAGSHIP)

        return success

    def vanguard_change(self):
        """
        Change vanguard, then apply its equipment preset (record 1).

        Returns:
            bool: True if vanguard changed
        """
        logger.hr('Change vanguard', level=1)
        logger.attr('ChangeVanguard', self.config.GemsFarming_ChangeVanguard)
        self.fleet_enter(self.fleet_to_attack)

        if self.CHANGE_EQUIP:
            logger.hr('Unload vanguard equipment', level=2)
            self._unload_equipment(FLEET_DETAIL_ENTER)

        logger.hr('Change vanguard', level=2)
        success = self.vanguard_change_execute()

        if self.CHANGE_EQUIP:
            logger.hr('Equip vanguard preset', level=2)
            self._equip_preset(FLEET_DETAIL_ENTER)

        return success

    def _dock_reset(self):
        self.dock_favourite_set(False, wait_loading=False)
        self.dock_sort_method_dsc_set(wait_loading=False)
        self.dock_filter_set()

    def _ship_change_confirm(self, button):
        self.dock_select_one(button)
        self._dock_reset()
        self.dock_select_confirm(check_button=page_fleet.check_button)

    def get_common_rarity_cv(self):
        """
        Get a common rarity cv by config.GemsFarming_CommonCV
        If config.GemsFarming_CommonCV == 'any', return a common lv1 ~ lv33 cv

        _dock_reset() needs to be called later.

        Returns:
            Ship:
        """
        self.dock_favourite_set(False, wait_loading=False)
        self.dock_sort_method_dsc_set(False, wait_loading=False)
        self.dock_filter_set(
            index='cv', rarity='common', extra='enhanceable', sort='total')

        logger.hr('FINDING FLAGSHIP')

        scanner = ShipScanner(level=(1, 31), emotion=(10, 150),
                              fleet=self.fleet_to_attack, status='free')
        scanner.disable('rarity')

        if self.config.GemsFarming_CommonCV == 'any':

            ships = scanner.scan(self.device.image)
            if ships:
                # Don't need to change current
                return ships

            # Change to any ship
            scanner.set_limitation(fleet=0)
            return scanner.scan(self.device.image, output=False)

        else:
            template = {
                'BOGUE': TEMPLATE_BOGUE,
                'HERMES': TEMPLATE_HERMES,
                'LANGLEY': TEMPLATE_LANGLEY,
                'RANGER': TEMPLATE_RANGER
            }[f'{self.config.GemsFarming_CommonCV.upper()}']

            ships = scanner.scan(self.device.image)
            if ships:
                # Don't need to change current
                return ships

            scanner.set_limitation(fleet=0)
            candidates = [ship for ship in scanner.scan(self.device.image, output=False)
                          if template.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]

            if candidates:
                # Change to specific ship
                return candidates

            logger.info('No specific CV was found, try reversed order.')
            self.dock_sort_method_dsc_set(True)

            candidates = [ship for ship in scanner.scan(self.device.image)
                          if template.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]

            return candidates

    def get_common_rarity_dd(self):
        """
        Get a common rarity dd with level is 100 (70 for servers except CN) and emotion > 10

        _dock_reset() needs to be called later.

        Returns:
            Ship:
        """
        if self.config.GemsFarming_CommonDD == 'any':
            faction = ['eagle', 'iron']
        elif self.config.GemsFarming_CommonDD == 'favourite':
            faction = 'all'
        elif self.config.GemsFarming_CommonDD == 'z20_or_z21':
            faction = 'iron'
        elif self.config.GemsFarming_CommonDD in ['aulick_or_foote', 'cassin_or_downes']:
            faction = 'eagle'
        else:
            logger.error(f'Invalid CommonDD setting: {self.config.GemsFarming_CommonDD}')
            raise ScriptError('Invalid GemsFarming_CommonDD')

        favourite = self.config.GemsFarming_CommonDD == 'favourite'
        self.dock_favourite_set(favourite, wait_loading=False)
        self.dock_sort_method_dsc_set(True, wait_loading=False)
        self.dock_filter_set(
            index='dd', rarity='common', faction=faction, extra='can_limit_break')

        logger.hr('FINDING VANGUARD')

        if self.config.SERVER in ['cn']:
            max_level = 100
        else:
            max_level = 70

        scanner = ShipScanner(level=(max_level, max_level), emotion=(10, 150),
                              fleet=[0, self.fleet_to_attack], status='free')
        scanner.disable('rarity')

        if self.config.GemsFarming_CommonDD in ['any', 'favourite', 'z20_or_z21']:
            # Change to any ship
            return scanner.scan(self.device.image)

        candidates = self.find_candidates(self.get_templates(self.config.GemsFarming_CommonDD), scanner)
        if candidates:
            # Change to specific ship
            return candidates

        logger.info('No specific DD was found, try reversed order.')
        self.dock_sort_method_dsc_set(False)

        # Change specific ship
        candidates = self.find_candidates(self.get_templates(self.config.GemsFarming_CommonDD), scanner)
        return candidates

    def find_candidates(self, template, scanner):
        """
        Find candidates based on template matching using a scanner.

        """
        candidates = []
        for item in template:
            candidates = [ship for ship in scanner.scan(self.device.image, output=False)
                          if item.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]
            if candidates:
                break
        return candidates

    @staticmethod
    def get_templates(common_dd):
        """
        Returns the corresponding template list based on CommonDD
        """
        if common_dd == 'aulick_or_foote':
            return [
                TEMPLATE_AULICK,
                TEMPLATE_FOOTE
            ]
        elif common_dd == 'cassin_or_downes':
            return [
                TEMPLATE_CASSIN_1, TEMPLATE_CASSIN_2,
                TEMPLATE_DOWNES_1, TEMPLATE_DOWNES_2
            ]
        else:
            logger.error(f'Invalid CommonDD setting: {common_dd}')
            raise ScriptError(f'Invalid CommonDD setting: {common_dd}')

    def flagship_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        for _ in self.loop():
            if self.appear(DOCK_CHECK, offset=(20, 20)):
                break
            if self.ui_page_appear(page_fleet, interval=5):
                self.device.click(FLEET_ENTER_FLAGSHIP)
                continue
            # 2025.05.29 game tips that infos skin feature when you enter dock
            if self.handle_game_tips():
                return True

        ship = self.get_common_rarity_cv()
        if ship:
            self._ship_change_confirm(min(ship, key=lambda s: (s.level, -s.emotion)).button)

            logger.info('Change flagship success')
            return True
        else:
            logger.info('Change flagship failed, no CV in common rarity.')
            self._dock_reset()
            self.ui_back(check_button=page_fleet.check_button)
            return False

    def vanguard_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        for _ in self.loop():
            if self.appear(DOCK_CHECK, offset=(20, 20)):
                break
            if self.ui_page_appear(page_fleet, interval=5):
                self.device.click(FLEET_ENTER)
                continue
            # 2025.05.29 game tips that infos skin feature when you enter dock
            if self.handle_game_tips():
                return True

        ship = self.get_common_rarity_dd()
        if ship:
            self._ship_change_confirm(max(ship, key=lambda s: s.emotion).button)

            logger.info('Change vanguard ship success')
            return True
        else:
            logger.info('Change vanguard ship failed, no DD in common rarity.')
            self._dock_reset()
            self.ui_back(check_button=page_fleet.check_button)
            return False

    _trigger_lv32 = False
    _trigger_emotion = False

    def triggered_stop_condition(self, oil_check=True):
        # Lv32 limit
        if self.campaign.config.LV32_TRIGGERED:
            self._trigger_lv32 = True
            logger.hr('TRIGGERED LV32 LIMIT')
            return True

        if self.campaign.map_is_auto_search and self.campaign.config.GEMS_EMOTION_TRIGGERED:
            self._trigger_emotion = True
            logger.hr('TRIGGERED EMOTION LIMIT')
            return True

        return super().triggered_stop_condition(oil_check=oil_check)

    def run(self, name, folder='campaign_main', mode='normal', total=0):
        """
        Args:
            name (str): Name of .py file.
            folder (str): Name of the file folder under campaign.
            mode (str): `normal` or `hard`
            total (int):
        """
        self.config.override(STOP_IF_REACH_LV32=True)

        while 1:
            self._trigger_lv32 = False
            is_limit = self.config.StopCondition_RunCount

            try:
                super().run(name=name, folder=folder, total=total)
            except CampaignEnd as e:
                if e.args[0] == 'Emotion withdraw':
                    self._trigger_emotion = True
                else:
                    raise e

            # End
            if self._trigger_lv32 or self._trigger_emotion:
                success = self.flagship_change()
                if self.change_vanguard:
                    success = success and self.vanguard_change()

                if is_limit and self.config.StopCondition_RunCount <= 0:
                    logger.hr('Triggered stop condition: Run count')
                    self.config.StopCondition_RunCount = 0
                    self.config.Scheduler_Enable = False
                    break

                self._trigger_lv32 = False
                self._trigger_emotion = False
                self.campaign.config.LV32_TRIGGERED = False
                self.campaign.config.GEMS_EMOTION_TRIGGERED = False

                # Scheduler
                if self.config.task_switched():
                    self.campaign.ensure_auto_search_exit()
                    self.config.task_stop()
                elif not success:
                    self.campaign.ensure_auto_search_exit()
                    self.config.task_delay(minute=30)
                    self.config.task_stop()

                continue
            else:
                break
