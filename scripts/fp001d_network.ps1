# Pure policy plus read-only snapshot. No network settings are changed here.
function Test-Fp001dNetworkState {
    param([array]$Adapters, [array]$Routes)
    $Reasons = @()
    $Ignored = @()
    $InertMiniports = @('WAN Miniport (Network Monitor)', 'WAN Miniport (IP)', 'WAN Miniport (IPv6)')
    if ($Adapters.Count -eq 0) { $Reasons += 'No adapter inventory available' }
    foreach ($Adapter in $Adapters) {
        if ($Adapter.Status -ne 'Up') { continue }
        $BoundRoutes = @($Routes | Where-Object { $_.InterfaceIndex -eq $Adapter.ifIndex })
        if ($Adapter.InterfaceDescription -in $InertMiniports -and $BoundRoutes.Count -eq 0) {
            # Explicit Windows bookkeeping miniports only. A routed miniport remains blocking.
            $Ignored += $Adapter.ifIndex
        } else {
            $Reasons += "Up adapter: $($Adapter.Name) [$($Adapter.InterfaceDescription)]"
        }
    }
    foreach ($Route in $Routes) {
        if ($Route.DestinationPrefix -in @('0.0.0.0/0', '::/0')) {
            $Reasons += "Default route: $($Route.DestinationPrefix) via $($Route.NextHop), interface $($Route.InterfaceIndex)"
        }
    }
    return @{isolated=($Reasons.Count -eq 0); reasons=@($Reasons); unrouted_bookkeeping_miniports=@($Ignored)}
}
function Get-Fp001dNetworkSnapshot {
    $ErrorActionPreference = 'Stop'
    $Adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Select-Object Name,InterfaceDescription,Status,ifIndex,MacAddress)
    $Routes = @(Get-NetRoute -PolicyStore ActiveStore -ErrorAction Stop | Select-Object DestinationPrefix,NextHop,InterfaceIndex,State)
    $Policy = Test-Fp001dNetworkState -Adapters $Adapters -Routes $Routes
    return @{
        timestamp=[DateTime]::UtcNow.ToString('o'); isolated=$Policy.isolated
        adapters=$Adapters; routes=$Routes; reasons=$Policy.reasons
        unrouted_bookkeeping_miniports=$Policy.unrouted_bookkeeping_miniports
    }
}
