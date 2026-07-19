import os
import shutil
from src import utils

class EditorLogic:
    """
    Handles the data and business logic for the Mapping Editor,
    decoupled from the UI.
    """
    def __init__(self):
        self.mappings = {}
        self.config = {}          # reserved _config contents (e.g. naming scheme)
        self.mapping_path = None
        self.template_dir = None
        self.is_dirty = False

    def load_mapping_file(self, file_path):
        """Loads a mapping file and its associated template directory."""
        self.mapping_path = file_path
        self.template_dir = self._get_template_dir(file_path)
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)
        
        if utils.MappingUtils.is_valid_mapping_file(self.mapping_path):
            data = utils.MappingUtils.load_mapping(self.mapping_path)
        else:
            data = {}
        # Keep the reserved _config (e.g. naming scheme) aside so the rules table
        # shows only real rules; it's merged back on save.
        self.config = data.pop("_config", {}) if isinstance(data.get("_config"), dict) else {}
        self.mappings = data
        self.is_dirty = False
        return True

    def save_mappings(self):
        """Saves the current mappings (and any reserved config) to the file."""
        if not self.mapping_path:
            return False, "No mapping file selected."
        try:
            data = {"_config": self.config, **self.mappings} if self.config else dict(self.mappings)
            utils.MappingUtils.save_mapping(self.mapping_path, data)
            self.is_dirty = False
            return True, "Mapping saved successfully."
        except Exception as e:
            return False, f"Could not save mapping:\n{e}"

    def get_naming_scheme(self):
        """The configured filename scheme (empty string if none)."""
        return self.config.get("naming_scheme", "")

    def set_naming_scheme(self, scheme):
        """Set/clear the filename scheme; marks dirty only on an actual change."""
        scheme = (scheme or "").strip()
        if scheme == self.config.get("naming_scheme", ""):
            return
        if scheme:
            self.config["naming_scheme"] = scheme
        else:
            self.config.pop("naming_scheme", None)
        self.is_dirty = True

    def add_rule(self, phrase, name, dest, match=None):
        """Adds a new mapping rule. An optional match block carries advanced
        (all/any/none) matching; omitted for simple rules."""
        if phrase in self.mappings:
            return False, "This phrase or keyword already exists."
        self.mappings[phrase] = self._build_rule(name, dest, match)
        self.is_dirty = True
        return True, None

    def update_rule(self, old_phrase, new_phrase, new_name, new_dest, match=None):
        """Updates an existing mapping rule."""
        if new_phrase != old_phrase and new_phrase in self.mappings:
            return False, "This phrase or keyword already exists."
        # Remove old one if phrase changed
        if old_phrase in self.mappings and new_phrase != old_phrase:
            del self.mappings[old_phrase]
        self.mappings[new_phrase] = self._build_rule(new_name, new_dest, match)
        self.is_dirty = True
        return True, None

    @staticmethod
    def _build_rule(name, dest, match=None):
        """Assemble a rule dict, including a match block only when one is given
        (so simple rules stay as compact as before)."""
        rule = {"name": name, "dest": dest}
        if match:
            rule["match"] = match
        return rule

    def remove_rule(self, phrase):
        """Removes a mapping rule."""
        if phrase in self.mappings:
            del self.mappings[phrase]
            self.is_dirty = True
        return True, None

    def move_rule(self, phrase, direction):
        """Moves a rule up or down in the order."""
        keys = list(self.mappings.keys())
        try:
            index = keys.index(phrase)
        except ValueError:
            return False
        
        if direction == "up" and index > 0:
            keys.insert(index - 1, keys.pop(index))
        elif direction == "down" and index < len(keys) - 1:
            keys.insert(index + 1, keys.pop(index))
        else:
            return False # No move was possible

        self.mappings = {k: self.mappings[k] for k in keys}
        self.is_dirty = True
        return True

    def rename_template_folder(self, old_rel_path, new_folder_name):
        """Renames a folder in the template directory and updates mappings."""
        old_abs_path = os.path.join(self.template_dir, old_rel_path)
        new_rel_path = os.path.join(os.path.dirname(old_rel_path), new_folder_name)
        new_abs_path = os.path.join(self.template_dir, new_rel_path)

        if os.path.exists(new_abs_path):
            return False, "A folder with that name already exists."
        
        try:
            os.rename(old_abs_path, new_abs_path)
        except Exception as e:
            return False, f"Could not rename folder:\n{e}"

        # Update mappings
        for phrase, rule in self.mappings.items():
            dest = rule.get("dest", ".")
            if not dest or dest == ".": continue
            norm_dest = os.path.normpath(dest)
            norm_old = os.path.normpath(old_rel_path)
            if norm_dest == norm_old or norm_dest.startswith(norm_old + os.sep):
                new_dest = os.path.normpath(norm_dest.replace(norm_old, new_rel_path, 1))
                self.mappings[phrase]["dest"] = new_dest
        
        self.is_dirty = True
        return True, None

    def autobuild_template_tree(self):
        """Creates template folders based on destinations in the mappings."""
        if not self.template_dir: return 0
        created = 0
        destinations = {rule.get("dest", ".") for rule in self.mappings.values()}
        for dest in destinations:
            if not dest or dest == ".": continue
            folder_path = os.path.join(self.template_dir, dest)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path, exist_ok=True)
                created += 1
        return created

    def get_all_destinations(self):
        """Get all possible destination folders from the template directory."""
        destinations = []
        if self.template_dir and os.path.exists(self.template_dir):
            for root, dirs, _ in os.walk(self.template_dir):
                for d in sorted(dirs):
                    full_path = os.path.join(root, d)
                    rel_path = os.path.relpath(full_path, self.template_dir)
                    destinations.append(rel_path)
            destinations.sort()
            destinations.insert(0, ".")
        return destinations

    def _get_template_dir(self, mapping_path):
        base, _ = os.path.splitext(mapping_path)
        return base + "_template"
