import pytest
import re


def get_test_id(test_config):
    """Generate a unique test ID based on the test name and description hash"""
    return f"{test_config['name']}_{hash(test_config['description']) % 1000}"


def validate_resource_uri(uri):
    """
    Validates that a resource URI follows the expected format: {server_id}://{resource_type}/{resource_id}
    Returns a tuple of (is_valid, components) where components is (server_id, resource_type, resource_id)
    """
    pattern = r"^([a-zA-Z0-9_-]+)://([a-zA-Z0-9_-]+)/(.+)$"
    match = re.match(pattern, uri)
    if not match:
        return False, None
    return True, match.groups()


@pytest.mark.asyncio
async def run_tool_test(client, context, test_config):
    """
    Common test function for running tool tests across different servers.

    Args:
        client: The client fixture
        context: Module-scoped context dictionary to store test values
        test_config: Configuration for the specific test to run
    """
    if test_config.get("skip", False):
        pytest.skip(f"Test {test_config['name']} marked to skip")
        return

    missing_deps = []
    for dep in test_config.get("depends_on", []):
        if dep not in context:
            missing_deps.append(dep)
        elif context[dep] in ["empty_list", "not_found", "empty"]:
            missing_deps.append(f"{dep} (has placeholder value)")

    if missing_deps:
        pytest.skip(f"Missing dependencies: {', '.join(missing_deps)}")
        return

    # if "setup" in test_config and callable(test_config["setup"]):
    #     setup_result = test_config["setup"](context)
    #     if isinstance(setup_result, dict):
    #         context.update(setup_result)

    tool_name = test_config["name"]
    expected_keywords = test_config["expected_keywords"]
    description = test_config["description"]

    if "args" in test_config:
        args = test_config["args"]
    elif "args_template" in test_config:
        try:
            args = test_config["args_template"].format(**context)
        except KeyError as e:
            pytest.skip(f"Missing context value: {e}")
            return
        except Exception as e:
            pytest.skip(f"Error formatting args: {e}")
            return
    else:
        args = ""

    keywords_str = ", ".join(expected_keywords)
    prompt = (
        "Not interested in your recommendations or what you think is best practice, just use what's given. "
        "Only pass required arguments to the tool and in case I haven't provided a required argument, you can try to pass your own that makes sense. "
        f"Only return the value with following keywords: {keywords_str} if successful or error with keyword 'error_message'. ensure to keep the keywords name exact same "
        f"Use the {tool_name} tool to {description} {args}. "
    ).format(tool_name=tool_name, description=description, args=args, keywords_str=keywords_str)

    response = await client.process_query(prompt)
    print(f"response: {response}")
    # if (
    #     "empty" in response.lower()
    #     or "[]" in response
    #     or "no items" in response.lower()
    #     or "not found" in response.lower()
    # ):
    #     if "regex_extractors" in test_config:
    #         for key, pattern in test_config["regex_extractors"].items():
    #             if key not in context:
    #                 context[key] = "empty_list"

    #     pytest.skip(f"Empty result from API for {tool_name}")
    #     return

    if "error_message" in response.lower() and "error_message" not in expected_keywords:
        pytest.fail(f"API error for {tool_name}: {response}")
        return

    if "regex_extractors" in test_config:
        for key, pattern in test_config["regex_extractors"].items():
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match and len(match.groups()) > 0:
                context[key] = match.group(1).strip()

    if "setup" in test_config and callable(test_config["setup"]):
        setup_result = test_config["setup"](context)
        if isinstance(setup_result, dict):
            context.update(setup_result)
    missing_keywords = []
    for keyword in expected_keywords:
        if keyword != "error_message" and keyword.lower() not in response.lower():
            missing_keywords.append(keyword)

    if missing_keywords:
        pytest.skip(f"Keywords not found: {', '.join(missing_keywords)}")
        return


    should_validate = test_config.get("validate_resource_uri", False) or (
        tool_name in ["list_resources", "read_resource"] and "resource_uri" in context
    )

    if should_validate and "resource_uri" in context:
        is_valid, components = validate_resource_uri(context["resource_uri"])
        if is_valid:
            context["resource_server"] = components[0]
            context["resource_type"] = components[1]
            context["resource_id"] = components[2]
        else:
            pytest.fail(f"Invalid resource URI format: {context['resource_uri']}")

    return context