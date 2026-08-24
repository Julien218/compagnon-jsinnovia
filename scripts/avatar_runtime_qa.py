def evaluate_runtime_qa(size_mib, max_mib, qa, max_components=12, min_largest_ratio=0.80):
    errors = []
    if size_mib <= 0.01:
        errors.append("candidate_too_small")
    if size_mib > max_mib:
        errors.append("candidate_too_large")
    if not qa.get("armature") or not qa.get("bones"):
        errors.append("rig_missing")
    if "idle" not in qa.get("animations", []):
        errors.append("idle_animation_missing")
    if int(qa.get("connected_components", 0)) > max_components:
        errors.append("mesh_fragmented_too_many_components")
    if float(qa.get("largest_component_ratio", 0)) < min_largest_ratio:
        errors.append("mesh_fragmented_no_dominant_component")
    return errors
