using Test
using DealHostSDK

@testset "DealHostClient" begin
    client = DealHostClient(
        "https://dealhost.example.com///";
        token="test-token",
        timeout_seconds=5,
    )

    @test client.base_url == "https://dealhost.example.com"
    @test client.token == "test-token"
    @test client.timeout_seconds == 5
    @test_throws ArgumentError DealHostClient("")
    @test_throws ArgumentError DealHostClient("https://dealhost.example.com"; timeout_seconds=0)
end
