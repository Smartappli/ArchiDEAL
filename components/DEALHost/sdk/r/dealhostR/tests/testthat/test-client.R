test_that("dealhost_client normalizes and stores client configuration", {
  client <- dealhost_client(
    "https://dealhost.example.com///",
    token = "test-token",
    timeout_seconds = 5
  )

  expect_equal(client$base_url, "https://dealhost.example.com")
  expect_equal(client$token, "test-token")
  expect_equal(client$timeout_seconds, 5)
})

test_that("dealhost_client rejects invalid base URLs", {
  expect_error(dealhost_client(""), "base_url must be a non-empty string")
  expect_error(dealhost_client(NA_character_), "base_url must be a non-empty string")
  expect_error(dealhost_client("///"), "base_url must be a non-empty string")
  expect_error(
    dealhost_client("https://dealhost.example.com", timeout_seconds = 0),
    "timeout_seconds must be a positive number"
  )
})
