#' Create a DEALHost API client
#'
#' @param base_url Base URL of DEALHost (example: "https://dealhost.example.com").
#' @param token Optional bearer token.
#' @param timeout_seconds Request timeout in seconds.
#' @return A client object used by all SDK functions.
#' @export
dealhost_client <- function(base_url, token = NULL, timeout_seconds = 30) {
  if (!is.character(base_url) || length(base_url) != 1 || is.na(base_url)) {
    stop("base_url must be a non-empty string.", call. = FALSE)
  }
  normalized_base_url <- sub("/+$", "", base_url)
  if (!nzchar(normalized_base_url)) {
    stop("base_url must be a non-empty string.", call. = FALSE)
  }
  if (!is.numeric(timeout_seconds) || length(timeout_seconds) != 1 ||
      is.na(timeout_seconds) || timeout_seconds <= 0) {
    stop("timeout_seconds must be a positive number.", call. = FALSE)
  }

  list(
    base_url = normalized_base_url,
    token = token,
    timeout_seconds = timeout_seconds
  )
}

.dealhost_request <- function(client, method, path, body = NULL, query = NULL) {
  request <- httr2::request(paste0(client$base_url, path))
  request <- httr2::req_method(request, method)
  request <- httr2::req_timeout(request, client$timeout_seconds)
  request <- httr2::req_headers(request, "Accept" = "application/json")

  if (!is.null(client$token) && nzchar(client$token)) {
    request <- httr2::req_auth_bearer_token(request, client$token)
  }
  if (!is.null(query)) {
    query <- query[!vapply(query, is.null, logical(1))]
    if (length(query) > 0) {
      request <- do.call(httr2::req_url_query, c(list(request), query))
    }
  }
  if (!is.null(body)) {
    request <- httr2::req_body_json(request, body, auto_unbox = TRUE)
  }

  response <- httr2::req_perform(request)
  httr2::resp_body_json(response, simplifyVector = TRUE)
}

#' Create a tool
#'
#' @param client Client created by [dealhost_client()].
#' @param name Tool name.
#' @param slug Tool slug.
#' @param description Optional description.
#' @param module_ids Integer vector of module IDs.
#' @param enabled Logical enabled state.
#' @return Parsed JSON response.
#' @export
create_tool <- function(client, name, slug, description = "", module_ids = integer(), enabled = TRUE) {
  body <- list(
    name = name,
    slug = slug,
    description = description,
    module_ids = as.integer(module_ids),
    enabled = enabled
  )
  .dealhost_request(client, "POST", "/api/hosting/tools/", body = body)
}

#' Create an application
#'
#' @param client Client created by [dealhost_client()].
#' @param name Application name.
#' @param slug Application slug.
#' @param description Optional description.
#' @param module_ids Integer vector of module IDs.
#' @param enabled Logical enabled state.
#' @return Parsed JSON response.
#' @export
create_application <- function(client, name, slug, description = "", module_ids = integer(), enabled = TRUE) {
  body <- list(
    name = name,
    slug = slug,
    description = description,
    module_ids = as.integer(module_ids),
    enabled = enabled
  )
  .dealhost_request(client, "POST", "/api/hosting/applications/", body = body)
}

#' Update a tool
#'
#' @param client Client created by [dealhost_client()].
#' @param tool_id Tool ID.
#' @param fields Named list of fields to patch.
#' @return Parsed JSON response.
#' @export
update_tool <- function(client, tool_id, fields) {
  .dealhost_request(client, "PATCH", paste0("/api/hosting/tools/", tool_id, "/"), body = fields)
}

#' Update an application
#'
#' @param client Client created by [dealhost_client()].
#' @param application_id Application ID.
#' @param fields Named list of fields to patch.
#' @return Parsed JSON response.
#' @export
update_application <- function(client, application_id, fields) {
  .dealhost_request(
    client,
    "PATCH",
    paste0("/api/hosting/applications/", application_id, "/"),
    body = fields
  )
}

#' List tools
#'
#' @param client Client created by [dealhost_client()].
#' @param enabled Optional logical filter.
#' @param module_slug Optional module slug filter.
#' @return Parsed JSON response.
#' @export
list_tools <- function(client, enabled = NULL, module_slug = NULL) {
  query <- list(
    enabled = if (!is.null(enabled)) tolower(as.character(enabled)) else NULL,
    module_slug = module_slug
  )
  .dealhost_request(client, "GET", "/api/hosting/tools/", query = query)
}

#' List applications
#'
#' @param client Client created by [dealhost_client()].
#' @param enabled Optional logical filter.
#' @param module_slug Optional module slug filter.
#' @return Parsed JSON response.
#' @export
list_applications <- function(client, enabled = NULL, module_slug = NULL) {
  query <- list(
    enabled = if (!is.null(enabled)) tolower(as.character(enabled)) else NULL,
    module_slug = module_slug
  )
  .dealhost_request(client, "GET", "/api/hosting/applications/", query = query)
}
