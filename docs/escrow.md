
# Simple Escrow Smart Contract

## Overview

As part of the shoBITCOIN project, I built and deployed a simple Ethereum escrow smart contract on the Sepolia testnet.

The goal was to understand how ETH moves between a buyer, a smart contract, and a seller, and how blockchain transactions can be verified independently using a block explorer.

## What I Built

The `SimpleEscrow` contract allows:

1. A buyer to deposit ETH into the smart contract.
2. The contract to hold the ETH temporarily.
3. The buyer to release the ETH to the seller.
4. The buyer to request a refund.
5. Anyone to read the current ETH balance of the contract.

## Architecture

```text
Buyer Wallet
     |
     | deposit ETH
     v
SimpleEscrow Smart Contract
     |
     | release()
     v
Seller Wallet
```

## Key Concepts Learned

### Smart Contract

A smart contract is a program deployed to a blockchain. Once deployed, users can interact with its functions through blockchain transactions.

### Buyer and Seller

The contract stores two Ethereum addresses:

* `buyer` — the wallet that deploys the contract
* `seller` — the address provided during deployment

The contract uses `msg.sender` to identify the account that initiated a transaction.

### Deployment

Deploying the contract creates the smart contract on Ethereum.

Deployment does **not** transfer ETH to the seller.

The account deploying the contract pays the blockchain transaction fee (gas).

### Deposit

The buyer calls the `deposit()` function and sends ETH with the transaction.

For this test:

```text
Deposit: 0.001 SepoliaETH
```

The contract balance was then checked using `getBalance()`.

The blockchain returned:

```text
1000000000000000 Wei
```

which equals:

```text
0.001 ETH
```

### Release

The buyer calls `release()`.

The smart contract then transfers its balance to the seller:

```solidity
(bool success, ) = payable(seller).call{value: amount}("");
```

The buyer pays the gas for calling `release()`, while the ETH held by the contract is transferred to the seller.

### Gas

Gas is the fee paid for executing transactions on Ethereum.

Gas is separate from the ETH being transferred.

During testing, the final release transaction had an actual transaction fee of:

```text
0.000089240625391664 ETH
```

### Wei

Ethereum represents ETH internally in Wei.

```text
1 ETH = 1,000,000,000,000,000,000 Wei

0.001 ETH = 1,000,000,000,000,000 Wei
```

## On-Chain Verification

After calling `release()`, the escrow balance was checked again:

```text
getBalance() → 0
```

The transaction was then inspected on Sepolia Etherscan.

The internal transaction showed:

```text
From: SimpleEscrow contract
To: Seller address
Amount: 0.001 ETH
```

This demonstrated that the smart contract executed the transfer rather than the buyer directly sending ETH to the seller.

## Transaction Lifecycle

```text
1. Deploy
Buyer → Ethereum
         |
         └── SimpleEscrow created

2. Deposit
Buyer → 0.001 ETH → SimpleEscrow

3. Verify
getBalance() → 0.001 ETH

4. Release
Buyer → release()

SimpleEscrow → 0.001 ETH → Seller

5. Verify
getBalance() → 0 ETH
```

## What I Learned

The biggest conceptual distinction from this exercise was:

> Deploying a smart contract is not the same as transferring cryptocurrency.

The contract must first exist on-chain. Users then interact with its functions through separate transactions.

I also learned how to distinguish between:

* A wallet address
* A smart contract address
* A blockchain transaction
* An internal contract transfer
* ETH and Wei
* Gas fees
* Read-only blockchain calls
* State-changing blockchain transactions

## Next Steps

The next phase of the shoBITCOIN project will focus on understanding more advanced Ethereum and DeFi mechanisms, including token swaps, liquidity, pricing, and decentralized financial applications.
