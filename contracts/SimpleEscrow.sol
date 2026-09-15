// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleEscrow {

    address public buyer;
    address public seller;

    constructor(address _seller) {
        buyer = msg.sender;
        seller = _seller;
    }

    function deposit() external payable {
        require(msg.sender == buyer, "Only buyer can deposit");
        require(msg.value > 0, "Must send ETH");
    }

    function release() external {
        require(msg.sender == buyer, "Only buyer can release");

        uint256 amount = address(this).balance;
        require(amount > 0, "No ETH in escrow");

        (bool success, ) = payable(seller).call{value: amount}("");
        require(success, "ETH transfer failed");
    }

    function refund() external {
        require(msg.sender == buyer, "Only buyer can refund");

        uint256 amount = address(this).balance;
        require(amount > 0, "No ETH in escrow");

        (bool success, ) = payable(buyer).call{value: amount}("");
        require(success, "ETH transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
